"""Manages Copilot SDK sessions for each Discord channel."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
from typing import Any

from copilot import CopilotClient
from copilot.session import PermissionHandler

from bot.config import DEFAULT_AI_MODEL, DEFAULT_REASONING_EFFORT
from bot.host_loader import HostConfig, load_model_content

log = logging.getLogger(__name__)


def _session_key(guild_id: int, channel_id: int) -> str:
    return f"{guild_id}_{channel_id}"


class ActiveSession:
    """Wraps a Copilot SDK session with a persistent event listener."""

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
        self.sent_message_ids: set[int] = set()

        # Persistent listener state
        self._message_callback: Any | None = None  # async fn(str) -> None
        self._unsubscribe: Any | None = None
        self._idle_event: asyncio.Event | None = None
        self._reply_count: int = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_message_callback(self, callback: Any) -> None:
        """Set the async callback for forwarding assistant messages (e.g. to Discord)."""
        self._message_callback = callback

    def setup_listener(self) -> None:
        """Subscribe to session events once. Stays active until cleanup()."""
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
                self._reply_count += 1
                if self._message_callback and self._loop:
                    asyncio.run_coroutine_threadsafe(_safe_send(event.data.content), self._loop)
            elif etype == "session.idle":
                if self._idle_event:
                    self._idle_event.set()

        self._unsubscribe = self.session.on(_on_event)

    def cleanup(self) -> None:
        """Unsubscribe the persistent listener."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None


class SessionManager:
    def __init__(self) -> None:
        self._client: CopilotClient | None = None
        self._sessions: dict[str, ActiveSession] = {}
        self._available_models: list[str] | None = None

    async def start(self) -> None:
        self._client = CopilotClient()
        await self._client.start()
        log.info("Copilot SDK client started")

        # Verify authentication via SDK
        auth = await self._client.get_auth_status()
        if auth.isAuthenticated:
            log.info(
                "Copilot authenticated (user=%s, type=%s)",
                auth.login or "unknown",
                auth.authType or "unknown",
            )
            return

        # Not authenticated — stop the client and run interactive login
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

        # Restart the client after login
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

    async def get_available_models(self, refresh: bool = False) -> list[str]:
        """Return model IDs from Copilot SDK, cached for autocomplete use."""
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

    @staticmethod
    def _build_system_content(host_config: HostConfig) -> str:
        """Build the full system prompt from host config."""
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

    @staticmethod
    def _build_custom_agents(host_config: HostConfig) -> list[dict]:
        """Build the custom_agents list from host config agents."""
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

        # If a game module was selected, send its content as the first message.
        # Callback is not set yet, so the reply won't be forwarded to Discord.
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
        """Try to resume an existing session. Returns None if not resumable."""
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

    async def send_message(
        self,
        guild_id: int,
        channel_id: int,
        user_message: str,
        context: str | None = None,
    ) -> str:
        """Send a message and wait for idle. Replies are forwarded via the session callback.

        Returns a non-empty string only when something needs to be shown to the user
        (e.g. timeout with no replies). Otherwise returns empty string.
        """
        key = _session_key(guild_id, channel_id)
        active = self._sessions.get(key)
        if not active:
            raise RuntimeError(f"No active session for {key}")

        prompt_parts: list[str] = []
        if context:
            prompt_parts.append(
                f"以下是頻道中最近的對話紀錄，供你參考上下文：\n\n{context}\n\n---\n\n"
            )
        prompt_parts.append(user_message)
        full_prompt = "".join(prompt_parts)

        try:
            idle_reached = await self._wait_for_idle(active, full_prompt)
        except Exception as exc:
            if "Session not found" not in str(exc):
                raise
            log.warning("Session %s expired (backend dropped it), auto-recovering...", key)

            # Auto-recovery: drop stale session, try resume → create
            old_callback = active._message_callback
            active.cleanup()
            self._sessions.pop(key, None)
            host_config = active.host_config
            if host_config is None:
                raise RuntimeError(f"Session {key} expired and no host_config for recovery")

            recovered = await self.resume_session(
                guild_id,
                channel_id,
                host_config,
                active.ai_model,
                active.reasoning_effort,
            )
            if recovered is None:
                log.info("Resume failed for %s, creating fresh session", key)
                recovered = await self.create_session(
                    guild_id,
                    channel_id,
                    host_config,
                    active.ai_model,
                    active.model_name,
                    active.reasoning_effort,
                )

            # Transfer the callback to the recovered session
            if old_callback:
                recovered.set_message_callback(old_callback)
            log.info("Session recovered for %s, retrying message", key)
            idle_reached = await self._wait_for_idle(recovered, full_prompt)

        if not idle_reached and active._reply_count == 0:
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
        """Send a prompt and wait for session.idle. Returns True if idle reached, False on timeout."""
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
