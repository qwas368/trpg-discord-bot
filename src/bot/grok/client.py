"""封裝 xAI SDK，提供簡單的 Grok 呼叫介面。"""

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
    """以非同步形式包裝官方 xAI Python SDK。"""

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
        # 官方 SDK 是同步介面，這裡丟到 thread 避免卡住 Discord event loop。
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
            # Grok 本身不保留長期狀態，所以每次都重新附上近期對話。
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
