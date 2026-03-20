"""Manages Copilot SDK sessions for each Discord channel."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from copilot import CopilotClient, PermissionHandler

from bot.config import DEFAULT_AI_MODEL
from bot.host_loader import HostConfig, load_model_content

log = logging.getLogger(__name__)


def _session_key(guild_id: int, channel_id: int) -> str:
    return f"{guild_id}_{channel_id}"


class ActiveSession:
    """Wraps a Copilot SDK session with metadata."""

    def __init__(self, session: Any, host_type: str, ai_model: str, model_name: str | None):
        self.session = session
        self.host_type = host_type
        self.ai_model = ai_model
        self.model_name = model_name
        self.sent_message_ids: set[int] = set()


class SessionManager:
    def __init__(self) -> None:
        self._client: CopilotClient | None = None
        self._sessions: dict[str, ActiveSession] = {}

    async def start(self) -> None:
        self._client = CopilotClient()
        await self._client.start()
        log.info("Copilot SDK client started")

    async def stop(self) -> None:
        for key in list(self._sessions):
            await self.close_session_by_key(key)
        if self._client:
            await self._client.stop()
            self._client = None
        log.info("Copilot SDK client stopped")

    def is_hosting(self, guild_id: int, channel_id: int) -> bool:
        return _session_key(guild_id, channel_id) in self._sessions

    def get_session(self, guild_id: int, channel_id: int) -> ActiveSession | None:
        return self._sessions.get(_session_key(guild_id, channel_id))

    async def create_session(
        self,
        guild_id: int,
        channel_id: int,
        host_config: HostConfig,
        ai_model: str | None = None,
        model_name: str | None = None,
    ) -> ActiveSession:
        assert self._client is not None, "SessionManager not started"

        key = _session_key(guild_id, channel_id)
        if key in self._sessions:
            raise RuntimeError(f"Session already exists for {key}")

        chosen_model = ai_model or DEFAULT_AI_MODEL

        # Build system message from host config
        system_parts: list[str] = []
        if host_config.instructions:
            system_parts.append(host_config.instructions)
        for agent in host_config.agents:
            system_parts.append(f"# {agent.name}\n\n{agent.content}")

        system_content = "\n\n---\n\n".join(system_parts)

        # Prepend language and format instructions
        system_content = (
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

        session = await self._client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=chosen_model,
            session_id=key,
            system_message={"mode": "replace", "content": system_content},
        )

        active = ActiveSession(session, host_config.name, chosen_model, model_name)
        self._sessions[key] = active
        log.info("Session created: %s (host=%s, model=%s)", key, host_config.name, chosen_model)

        # If a game module was selected, send its content as the first message
        if model_name:
            try:
                content = load_model_content(model_name)
                await self._send_and_wait(
                    session,
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
    ) -> ActiveSession | None:
        """Try to resume an existing session. Returns None if not resumable."""
        assert self._client is not None, "SessionManager not started"

        key = _session_key(guild_id, channel_id)
        if key in self._sessions:
            return self._sessions[key]

        chosen_model = ai_model or DEFAULT_AI_MODEL

        try:
            session = await self._client.resume_session(
                session_id=key,
                on_permission_request=PermissionHandler.approve_all,
                model=chosen_model,
            )
            active = ActiveSession(session, host_config.name, chosen_model, None)
            self._sessions[key] = active
            log.info("Session resumed: %s", key)
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
        """Send a message to the session and return the assistant's reply."""
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

        return await self._send_and_wait(active.session, full_prompt)

    async def close_session(self, guild_id: int, channel_id: int) -> None:
        key = _session_key(guild_id, channel_id)
        await self.close_session_by_key(key)

    async def close_session_by_key(self, key: str) -> None:
        active = self._sessions.pop(key, None)
        if active:
            try:
                await active.session.disconnect()
            except Exception:
                log.warning("Error disconnecting session %s", key, exc_info=True)
            log.info("Session closed: %s", key)

    @staticmethod
    async def _send_and_wait(session: Any, prompt: str, timeout: float = 120.0) -> str:
        done = asyncio.Event()
        replies: list[str] = []

        def on_event(event: Any) -> None:
            etype = event.type if isinstance(event.type, str) else event.type.value
            if etype == "assistant.message":
                replies.append(event.data.content)
            elif etype == "session.idle":
                done.set()

        unsubscribe = session.on(on_event)
        try:
            await session.send(prompt)
            await asyncio.wait_for(done.wait(), timeout=timeout)
        finally:
            unsubscribe()

        return "\n\n".join(replies) if replies else "(沒有回覆)"
