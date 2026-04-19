"""管理每個 Discord 頻道對應的 Copilot / Grok 執行狀態。"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Sequence

from copilot import CopilotClient
from copilot.session import PermissionHandler

from bot.config import (
    DEFAULT_AI_MODEL,
    DEFAULT_GROK_MODEL,
    DEFAULT_REASONING_EFFORT,
    GROK_CONTEXT_MESSAGE_COUNT,
    XAI_API_KEY,
)
from bot.grok.client import GrokClient
from bot.host_loader import HostConfig, load_model_content

log = logging.getLogger(__name__)


def _session_key(guild_id: int, channel_id: int) -> str:
    """將 guild 與 channel 組成穩定的 session key。"""
    return f"{guild_id}_{channel_id}"


class ActiveSession:
    """包裝 Copilot SDK session，並補上切換 Grok 時需要的執行期狀態。"""

    def __init__(
        self,
        session: Any,
        host_type: str,
        ai_model: str,
        model_name: str | None,
        reasoning_effort: str | None,
        host_config: HostConfig | None = None,
    ):
        self.session = session
        self.host_type = host_type
        self.ai_model = ai_model
        self.model_name = model_name
        self.reasoning_effort = reasoning_effort
        self.host_config = host_config

        # sent_message_ids 用來避免把已經看過的 Discord 訊息再次送進 Copilot。
        self.sent_message_ids: set[int] = set()

        # mode / grok_* 這一組欄位負責維護 Grok 切換、回補與角色摘要狀態。
        self.mode = "copilot"
        self.grok_model = DEFAULT_GROK_MODEL
        self.grok_pending_lines: list[str] = []
        self.grok_pending_message_ids: set[int] = set()
        self.pending_copilot_backfill = False
        self.grok_started_at: datetime | None = None
        self.grok_character_summary: str | None = None

        # 底下是與 Copilot SDK subscription 相關的暫存狀態。
        self._message_callback: Any | None = None  # async fn(str) -> None
        self._unsubscribe: Any | None = None
        self._idle_event: asyncio.Event | None = None
        self._reply_count: int = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_message_callback(self, callback: Any) -> None:
        """設定 assistant 回覆的轉送 callback（通常是送回 Discord）。"""
        self._message_callback = callback

    def setup_listener(self) -> None:
        """訂閱 Copilot session 事件，直到 cleanup() 才解除。"""
        self._loop = asyncio.get_running_loop()

        async def _safe_send(content: str) -> None:
            if self._message_callback:
                try:
                    await self._message_callback(content)
                except Exception:
                    log.exception("Error in message callback")

        def _on_event(event: Any) -> None:
            etype = event.type if isinstance(event.type, str) else event.type.value
            if etype == "assistant.message" and event.data.content:
                # assistant.message 代表 Copilot 真正吐出了可轉送的內容。
                self._reply_count += 1
                if self._message_callback and self._loop:
                    asyncio.run_coroutine_threadsafe(_safe_send(event.data.content), self._loop)
            elif etype == "session.idle":
                # session.idle 代表這一輪輸出已經結束，可解除等待。
                if self._idle_event:
                    self._idle_event.set()

        self._unsubscribe = self.session.on(_on_event)

    def cleanup(self) -> None:
        """解除事件訂閱，避免 session 關閉後仍殘留 callback。"""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def copy_runtime_state_from(self, other: "ActiveSession") -> None:
        """在 session 自動恢復時沿用 mode、backfill 與摘要等執行期狀態。"""
        self.sent_message_ids = set(other.sent_message_ids)
        self.mode = other.mode
        self.grok_model = other.grok_model
        self.grok_pending_lines = list(other.grok_pending_lines)
        self.grok_pending_message_ids = set(other.grok_pending_message_ids)
        self.pending_copilot_backfill = other.pending_copilot_backfill
        self.grok_started_at = other.grok_started_at
        self.grok_character_summary = other.grok_character_summary

    def enable_grok_mode(self) -> None:
        """切到 Grok，並記錄切換時間供 backfill 判斷。"""
        self.mode = "grok"
        self.grok_started_at = datetime.now(timezone.utc)

    def disable_grok_mode(self) -> None:
        """切回 Copilot，標記下一次要先補回 Grok 期間 transcript。"""
        self.mode = "copilot"
        self.grok_started_at = None
        self.pending_copilot_backfill = bool(self.grok_pending_lines)

    def record_grok_backfill(
        self,
        message_id: int,
        content: str,
        created_at: datetime | None,
    ) -> None:
        """記錄 Grok 模式期間的 Discord 訊息，供切回 Copilot 時回補。"""
        if not content or message_id in self.grok_pending_message_ids:
            return

        # 某些 datetime 可能沒有 tzinfo，統一補成 UTC 以便和 grok_started_at 比較。
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if self.grok_started_at and created_at and created_at < self.grok_started_at:
            return

        self.grok_pending_message_ids.add(message_id)
        self.grok_pending_lines.append(content)
        self.pending_copilot_backfill = True

    def clear_grok_backfill(self) -> None:
        self.grok_pending_lines.clear()
        self.grok_pending_message_ids.clear()
        self.pending_copilot_backfill = False


class SessionManager:
    def __init__(self) -> None:
        self._client: CopilotClient | None = None
        self._sessions: dict[str, ActiveSession] = {}
        self._available_models: list[str] | None = None
        self._grok_client: GrokClient | None = None
        self._grok_init_error: str | None = None

        # 啟動時先嘗試初始化 Grok；若套件缺失，延後到使用者切換時再回報。
        if XAI_API_KEY:
            try:
                self._grok_client = GrokClient(XAI_API_KEY)
            except RuntimeError as exc:
                self._grok_init_error = str(exc)

    async def start(self) -> None:
        self._client = CopilotClient()
        await self._client.start()
        log.info("Copilot SDK client started")

        # 先透過 SDK 驗證是否已登入 Copilot。
        auth = await self._client.get_auth_status()
        if auth.isAuthenticated:
            log.info(
                "Copilot authenticated (user=%s, type=%s)",
                auth.login or "unknown",
                auth.authType or "unknown",
            )
            return

        # 尚未登入時，改走 copilot CLI 的互動式登入流程。
        log.warning("Copilot is not authenticated: %s", auth.statusMessage or "no details")
        await self._client.stop()
        self._client = None

        cli = shutil.which("copilot")
        if not cli:
            log.error("Copilot CLI not found in PATH. Cannot run login flow.")
            sys.exit(1)

        is_interactive = sys.stdin is not None and sys.stdin.isatty()
        if not is_interactive:
            log.error(
                "Copilot is not authenticated and stdin is not a terminal. "
                "Please run 'copilot login' manually first, then restart the bot."
            )
            sys.exit(1)

        log.info("Starting Copilot login flow...")
        result = subprocess.run(
            [cli, "login"],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        if result.returncode != 0:
            log.error("Copilot login failed (exit code %d).", result.returncode)
            sys.exit(1)

        # 登入成功後重建 SDK client，讓後續 session 能正常建立。
        self._client = CopilotClient()
        await self._client.start()
        auth = await self._client.get_auth_status()
        if not auth.isAuthenticated:
            log.error("Still not authenticated after login. Exiting.")
            sys.exit(1)
        log.info("Copilot authenticated after login (user=%s)", auth.login or "unknown")

    async def stop(self) -> None:
        for key in list(self._sessions):
            await self.close_session_by_key(key)
        if self._client:
            await self._client.stop()
            self._client = None
        self._available_models = None
        log.info("Copilot SDK client stopped")

    def is_hosting(self, guild_id: int, channel_id: int) -> bool:
        return _session_key(guild_id, channel_id) in self._sessions

    def get_session(self, guild_id: int, channel_id: int) -> ActiveSession | None:
        return self._sessions.get(_session_key(guild_id, channel_id))

    def require_session(self, guild_id: int, channel_id: int) -> ActiveSession:
        active = self.get_session(guild_id, channel_id)
        if not active:
            raise RuntimeError(f"No active session for {_session_key(guild_id, channel_id)}")
        return active

    async def get_available_models(self, refresh: bool = False) -> list[str]:
        """從 Copilot SDK 取得模型 ID，並做快取供 autocomplete 使用。"""
        assert self._client is not None, "SessionManager not started"

        if self._available_models is not None and not refresh:
            return self._available_models

        models = await self._client.list_models()
        ids = sorted(
            {
                model_id
                for model in models
                if (model_id := getattr(model, "id", None))
            }
        )
        self._available_models = ids or [DEFAULT_AI_MODEL]
        return self._available_models

    def is_grok_available(self) -> bool:
        return self._grok_client is not None

    def ensure_grok_available(self) -> GrokClient:
        if self._grok_client is not None:
            return self._grok_client
        if not XAI_API_KEY:
            raise RuntimeError("尚未設定 XAI_API_KEY，無法啟用 Grok 模式。")
        if self._grok_init_error:
            raise RuntimeError(self._grok_init_error)
        raise RuntimeError("Grok client 尚未初始化。")

    async def toggle_grok_mode(
        self,
        guild_id: int,
        channel_id: int,
        history_context: str | None = None,
        history_message_ids: Sequence[int] | None = None,
        ai_name: str | None = None,
    ) -> tuple[ActiveSession, bool]:
        """切換指定頻道的 Grok 模式，必要時先建立 handoff 摘要。"""
        active = self.require_session(guild_id, channel_id)
        if active.mode == "grok":
            active.disable_grok_mode()
            return active, False

        self.ensure_grok_available()

        # 從 Copilot 切到 Grok 時，先請 Copilot 用近期對話整理角色卡。
        context = history_context or f"（最近 {GROK_CONTEXT_MESSAGE_COUNT} 則訊息中沒有可用內容）"
        summary = await self.generate_grok_handoff_summary(
            guild_id,
            channel_id,
            context,
            history_message_ids or (),
            ai_name,
        )
        active.grok_character_summary = summary
        active.enable_grok_mode()
        return active, True

    async def generate_grok_handoff_summary(
        self,
        guild_id: int,
        channel_id: int,
        history_context: str,
        history_message_ids: Sequence[int],
        ai_name: str | None = None,
    ) -> str:
        """請 Copilot 根據 recent history 產出一份給 Grok 使用的角色摘要。"""
        active = self.require_session(guild_id, channel_id)
        if active.mode != "copilot":
            raise RuntimeError("只能在 Copilot 模式下建立 Grok 交接摘要。")

        prompt = self._build_grok_handoff_prompt(history_context, ai_name)
        summary = await self._send_internal_message(active, prompt)
        active.grok_character_summary = summary
        active.sent_message_ids.update(history_message_ids)
        log.info(
            "Generated Grok handoff summary for %s using %d recent messages",
            _session_key(guild_id, channel_id),
            len(history_message_ids),
        )
        return summary

    @staticmethod
    async def _send_internal_message(
        active: ActiveSession,
        prompt: str,
        timeout: float = 240.0,
    ) -> str:
        """送出不應回傳到 Discord 的內部 prompt，例如 handoff 摘要請求。"""
        original_callback = active._message_callback
        active._message_callback = None
        try:
            event = await active.session.send_and_wait(prompt, timeout=timeout)
        finally:
            active._message_callback = original_callback

        content = getattr(getattr(event, "data", None), "content", None) if event else None
        if not content or not str(content).strip():
            raise RuntimeError("Copilot 沒有成功產出 Grok 交接摘要。")
        return str(content).strip()

    @staticmethod
    def _build_system_content(host_config: HostConfig) -> str:
        """把 host 指令與 agents 組成 Copilot / Grok 共用的基礎 system prompt。"""
        system_parts: list[str] = []
        if host_config.instructions:
            system_parts.append(host_config.instructions)
        for agent in host_config.agents:
            system_parts.append(f"# {agent.name}\n\n{agent.content}")

        system_content = "\n\n---\n\n".join(system_parts)

        return (
            "你是一位 TRPG 主持人，請使用繁體中文回應所有對話。\n"
            "你的回覆會直接發送到 Discord 頻道，請遵守 Discord 的文字格式：\n"
            "- 使用 **粗體**、*斜體*、~~刪除線~~ 等 Markdown 語法\n"
            "- 使用 > 引用文字\n"
            "- 使用 ```區塊``` 來顯示程式碼或特殊排版\n"
            "- 不要使用 HTML 標籤\n"
            "- 不要使用 # 標題語法（Discord 不支援）\n"
            "- 頻道中有多位玩家，每則訊息會標註玩家名稱與 ID，請注意區分不同玩家\n\n"
            + system_content
        )

    @classmethod
    def _build_grok_system_content(
        cls,
        host_config: HostConfig,
        ai_name: str | None = None,
        character_summary: str | None = None,
    ) -> str:
        """建立 Grok 專用 system prompt，補上 stateless 說明與角色卡摘要。"""
        ai_identity = (
            f"你在這個 Discord 頻道中的名字是「{ai_name}」。玩家提到、呼叫或對話中稱呼這個名字時，指的就是你。\n"
            if ai_name
            else ""
        )
        summary_section = (
            f"以下是 Copilot 根據最近 {GROK_CONTEXT_MESSAGE_COUNT} 則 Discord 訊息整理的精簡角色卡。"
            "請盡量維持這些角色設定；若與更近的對話衝突，以更近的對話為準。\n\n"
            f"{character_summary}\n\n"
            if character_summary
            else ""
        )
        return (
            "你目前在一個 Discord 頻道中接續多人對話。\n"
            + ai_identity
            + "你不會持續保留跨回合記憶，請只根據本輪提供的最近對話紀錄與最新提及訊息來回應。\n"
            "如果上下文不足，直接依據已知內容接話，不要假裝看過未提供的內容。\n\n"
            + summary_section
            + cls._build_system_content(host_config)
        )

    @staticmethod
    def _build_grok_handoff_prompt(history_context: str, ai_name: str | None = None) -> str:
        """建立請 Copilot 整理角色卡的內部 handoff prompt。"""
        ai_identity = (
            f"在這個 Discord 頻道中，AI/主持人自己的名字是「{ai_name}」。\n"
            if ai_name
            else ""
        )
        return (
            "這是一則內部交接訊息，不要角色扮演，也不要產出要直接貼到 Discord 的回覆。\n"
            "接下來這個頻道將暫時由 Grok 接手回覆。\n"
            + ai_identity
            + f"請根據以下最近 {GROK_CONTEXT_MESSAGE_COUNT} 則 Discord 訊息，整理出「出現角色的精簡角色卡」。\n"
            "請優先涵蓋：姓名、身分/角色定位、個性、口吻/說話風格、與玩家的關係。\n"
            "若資訊不足，請明確寫「未知」。請只輸出繁體中文摘要，不要額外解釋。\n\n"
            "最近訊息如下：\n\n"
            f"{history_context}"
        )

    @staticmethod
    def _build_custom_agents(host_config: HostConfig) -> list[dict]:
        """將 HostConfig.agents 轉成 Copilot SDK 需要的 custom_agents 格式。"""
        return [
            {
                "name": agent.name,
                "prompt": agent.content,
                **({"description": agent.description} if agent.description else {}),
            }
            for agent in host_config.agents
        ]

    async def create_session(
        self,
        guild_id: int,
        channel_id: int,
        host_config: HostConfig,
        ai_model: str | None = None,
        model_name: str | None = None,
        reasoning_effort: str | None = None,
    ) -> ActiveSession:
        """建立一個新的 Copilot session，並掛上 Discord 端需要的執行期狀態。"""
        assert self._client is not None, "SessionManager not started"

        key = _session_key(guild_id, channel_id)
        if key in self._sessions:
            raise RuntimeError(f"Session already exists for {key}")

        chosen_model = ai_model or DEFAULT_AI_MODEL
        chosen_reasoning_effort = reasoning_effort or DEFAULT_REASONING_EFFORT
        system_content = self._build_system_content(host_config)
        custom_agents = self._build_custom_agents(host_config)

        session = await self._client.create_session(
            session_id=key,
            model=chosen_model,
            reasoning_effort=chosen_reasoning_effort,
            working_directory=str(host_config.host_dir),
            on_permission_request=PermissionHandler.approve_all,
            system_message={"mode": "replace", "content": system_content},
            custom_agents=custom_agents or None,
            skill_directories=host_config.skill_directories or None,
        )

        active = ActiveSession(
            session,
            host_config.name,
            chosen_model,
            model_name,
            chosen_reasoning_effort,
            host_config,
        )
        active.setup_listener()
        self._sessions[key] = active
        log.info(
            "Session created: %s (host=%s, model=%s, reasoning_effort=%s)",
            key,
            host_config.name,
            chosen_model,
            chosen_reasoning_effort or "(default)",
        )

        # 若有指定遊戲模組，先把模組內容作為開場資料送進 Copilot。
        # 此時 callback 尚未綁到 Discord，因此不會把初始化回覆送到頻道。
        if model_name:
            try:
                content = load_model_content(model_name)
                await self._wait_for_idle(
                    active,
                    f"以下是本次遊戲模組的資料，請仔細閱讀並據此主持遊戲：\n\n{content}",
                )
                log.info("Game module loaded: %s", model_name)
            except FileNotFoundError:
                log.warning("Game module not found: %s", model_name)

        return active

    async def resume_session(
        self,
        guild_id: int,
        channel_id: int,
        host_config: HostConfig,
        ai_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> ActiveSession | None:
        """嘗試恢復既有 session；若後端無法恢復則回傳 None。"""
        assert self._client is not None, "SessionManager not started"

        key = _session_key(guild_id, channel_id)
        if key in self._sessions:
            return self._sessions[key]

        chosen_model = ai_model or DEFAULT_AI_MODEL
        chosen_reasoning_effort = reasoning_effort or DEFAULT_REASONING_EFFORT

        system_content = self._build_system_content(host_config)
        custom_agents = self._build_custom_agents(host_config)

        try:
            session = await self._client.resume_session(
                key,
                on_permission_request=PermissionHandler.approve_all,
                model=chosen_model,
                reasoning_effort=chosen_reasoning_effort,
                working_directory=str(host_config.host_dir),
                system_message={"mode": "replace", "content": system_content},
                custom_agents=custom_agents or None,
                skill_directories=host_config.skill_directories or None,
            )
            active = ActiveSession(
                session,
                host_config.name,
                chosen_model,
                None,
                chosen_reasoning_effort,
                host_config,
            )
            active.setup_listener()
            self._sessions[key] = active
            log.info(
                "Session resumed: %s (model=%s, reasoning_effort=%s)",
                key,
                chosen_model,
                chosen_reasoning_effort or "(default)",
            )
            return active
        except Exception as e:
            log.debug("Could not resume session %s: %s", key, e)
            return None

    async def send_grok_message(
        self,
        guild_id: int,
        channel_id: int,
        user_message: str,
        context: str | None = None,
        ai_name: str | None = None,
    ) -> str:
        """把當前回合的 Discord 對話交給 Grok 產生回覆。"""
        active = self.require_session(guild_id, channel_id)
        if active.mode != "grok":
            raise RuntimeError("Current session is not in Grok mode.")
        if active.host_config is None:
            raise RuntimeError("Current session is missing host configuration.")

        grok_client = self.ensure_grok_available()
        return await grok_client.generate_reply(
            model=active.grok_model or DEFAULT_GROK_MODEL,
            system_prompt=self._build_grok_system_content(
                active.host_config,
                ai_name,
                active.grok_character_summary,
            ),
            context=context,
            user_message=user_message,
        )

    async def send_message(
        self,
        guild_id: int,
        channel_id: int,
        user_message: str,
        context: str | None = None,
    ) -> str:
        """將訊息送給 Copilot 並等待 idle。

        真正的模型回覆會透過 session callback 直接轉送到 Discord。
        這個方法只在需要額外提示使用者時回傳文字，例如完全逾時沒有任何輸出。
        """
        key = _session_key(guild_id, channel_id)
        active = self._sessions.get(key)
        if not active:
            raise RuntimeError(f"No active session for {key}")

        prompt_parts: list[str] = []
        if active.pending_copilot_backfill and active.grok_pending_lines:
            # 切回 Copilot 後，先把 Grok 期間漏掉的頻道訊息補給它。
            prompt_parts.append(
                "以下是你切換到 Grok 模式期間，Discord 頻道中發生但你尚未看過的對話。"
                "請先吸收這些內容，再接續最新的玩家訊息：\n\n"
                f"{chr(10).join(active.grok_pending_lines)}\n\n---\n\n"
            )
        if context:
            prompt_parts.append(
                f"以下是頻道中最近的對話紀錄，供你參考上下文：\n\n{context}\n\n---\n\n"
            )
        prompt_parts.append(user_message)
        full_prompt = "".join(prompt_parts)

        target_active = active

        try:
            idle_reached = await self._wait_for_idle(target_active, full_prompt)
        except Exception as exc:
            if "Session not found" not in str(exc):
                raise
            log.warning("Session %s expired (backend dropped it), auto-recovering...", key)

            # 後端 session 遺失時，先丟棄 stale session，再嘗試 resume，最後才重建。
            old_callback = target_active._message_callback
            target_active.cleanup()
            self._sessions.pop(key, None)
            host_config = target_active.host_config
            if host_config is None:
                raise RuntimeError(f"Session {key} expired and no host_config for recovery")

            recovered = await self.resume_session(
                guild_id,
                channel_id,
                host_config,
                target_active.ai_model,
                target_active.reasoning_effort,
            )
            if recovered is None:
                log.info("Resume failed for %s, creating fresh session", key)
                recovered = await self.create_session(
                    guild_id,
                    channel_id,
                    host_config,
                    target_active.ai_model,
                    target_active.model_name,
                    target_active.reasoning_effort,
                )

            recovered.copy_runtime_state_from(target_active)

            # 恢復成功後，把原本的 Discord callback 接回新 session。
            if old_callback:
                recovered.set_message_callback(old_callback)
            log.info("Session recovered for %s, retrying message", key)
            target_active = recovered
            idle_reached = await self._wait_for_idle(target_active, full_prompt)

        if target_active.pending_copilot_backfill and target_active.grok_pending_lines:
            target_active.sent_message_ids.update(target_active.grok_pending_message_ids)
            target_active.clear_grok_backfill()

        if not idle_reached and target_active._reply_count == 0:
            return "⚠️ 回覆逾時，請再試一次。"
        return ""

    async def close_session(self, guild_id: int, channel_id: int) -> None:
        key = _session_key(guild_id, channel_id)
        await self.close_session_by_key(key)

    async def close_session_by_key(self, key: str) -> None:
        active = self._sessions.pop(key, None)
        if active:
            active.cleanup()
            try:
                await active.session.disconnect()
            except Exception:
                log.warning("Error disconnecting session %s", key, exc_info=True)
            log.info("Session closed: %s", key)

    @staticmethod
    async def _wait_for_idle(active: ActiveSession, prompt: str, timeout: float = 240.0) -> bool:
        """送出 prompt 後等待 session.idle；逾時則回傳 False。"""
        active._idle_event = asyncio.Event()
        active._reply_count = 0
        try:
            await active.session.send(prompt)
            await asyncio.wait_for(active._idle_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            log.warning(
                "Session timed out after %.1f seconds (subscription remains active, replies=%d)",
                timeout,
                active._reply_count,
            )
            return False
        finally:
            active._idle_event = None
