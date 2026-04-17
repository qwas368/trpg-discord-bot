"""xAI Grok client wrapper."""

from __future__ import annotations

import asyncio

try:
    from xai_sdk import Client
    from xai_sdk.chat import system, user
except ImportError:  # pragma: no cover - handled at runtime
    Client = None
    system = None
    user = None


class GrokClient:
    """Small async wrapper around the official xAI Python SDK."""

    def __init__(self, api_key: str):
        if Client is None or system is None or user is None:
            raise RuntimeError("xai-sdk 尚未安裝，無法啟用 Grok 模式。")
        self._client = Client(api_key=api_key)

    async def generate_reply(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        context: str | None = None,
    ) -> str:
        return await asyncio.to_thread(
            self._generate_reply_sync,
            model,
            system_prompt,
            user_message,
            context,
        )

    def _generate_reply_sync(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        context: str | None,
    ) -> str:
        prompt_parts: list[str] = []
        if context:
            prompt_parts.append(
                f"以下是 Discord 頻道最近的對話紀錄，請依此接續對話：\n\n{context}\n\n---"
            )
        prompt_parts.append(f"以下是最新提及你的訊息：\n\n{user_message}")

        chat = self._client.chat.create(
            model=model,
            messages=[
                system(system_prompt),
                user("\n\n".join(prompt_parts)),
            ],
        )
        response = chat.sample()
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else str(content)
