"""Discord bot core — sets up the bot instance and message handling."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.config import DISCORD_TOKEN
from bot.copilot.session_manager import SessionManager

log = logging.getLogger(__name__)

CONTEXT_MESSAGE_COUNT = 20
DISCORD_MAX_LENGTH = 2000


def _chunk_message(text: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """Split a long message into chunks that fit Discord's character limit."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at a newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


class TRPGBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.session_manager = SessionManager()

    async def setup_hook(self) -> None:
        await self.session_manager.start()
        await self.load_extension("bot.cogs.hosting")
        synced = await self.tree.sync()
        log.info("Synced %d slash commands", len(synced))

    async def close(self) -> None:
        await self.session_manager.stop()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Bot ready as %s (ID: %s)", self.user, self.user.id if self.user else "?")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        # Only respond when mentioned in a hosted channel
        if not self.user or self.user not in message.mentions:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id

        if not self.session_manager.is_hosting(guild_id, channel_id):
            return

        async with message.channel.typing():
            # Collect recent context
            context_lines: list[str] = []
            async for msg in message.channel.history(limit=CONTEXT_MESSAGE_COUNT, before=message):
                author = msg.author.display_name
                context_lines.append(f"[{author}]: {msg.content}")
            context_lines.reverse()
            context = "\n".join(context_lines) if context_lines else None

            # Remove the bot mention from the user's message
            user_text = message.content
            if self.user:
                user_text = user_text.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()

            display_name = message.author.display_name
            prompt = f"[{display_name}]: {user_text}" if user_text else f"[{display_name}] 提及了你"

            try:
                reply = await self.session_manager.send_message(
                    guild_id, channel_id, prompt, context
                )
                for chunk in _chunk_message(reply):
                    await message.channel.send(chunk)
            except Exception:
                log.exception("Error processing message in %s/%s", guild_id, channel_id)
                await message.channel.send("⚠️ 處理訊息時發生錯誤，請稍後再試。")


def run_bot() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    bot = TRPGBot()
    bot.run(DISCORD_TOKEN)
