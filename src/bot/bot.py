"""Discord bot core — sets up the bot instance and message handling."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

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

        # Clear stale per-guild commands from previous bot configurations
        for guild in self.guilds:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Cleared guild-specific commands for: %s", guild.name)

        # Sync global commands (registers current commands, removes old ones)
        synced = await self.tree.sync()
        log.info("Synced %d slash commands", len(synced))

    async def close(self) -> None:
        await self.session_manager.stop()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Bot ready as %s (ID: %s)", self.user, self.user.id if self.user else "?")
        if self.guilds:
            for guild in self.guilds:
                log.info("  Connected to server: %s (ID: %d, members: %d)", guild.name, guild.id, guild.member_count or 0)
        else:
            log.info("  Not connected to any servers.")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("Joined server: %s (ID: %d)", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Left server: %s (ID: %d)", guild.name, guild.id)

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

        channel_name = getattr(message.channel, "name", str(channel_id))
        log.info(
            "Message from %s in #%s (guild=%d, channel=%d)",
            message.author.display_name, channel_name, guild_id, channel_id,
        )

        async with message.channel.typing():
            active = self.session_manager.get_session(guild_id, channel_id)
            if not active:
                return

            # Collect recent context, skipping messages already sent to the session
            context_lines: list[str] = []
            new_msg_ids: list[int] = []
            async for msg in message.channel.history(limit=CONTEXT_MESSAGE_COUNT, before=message):
                if msg.id in active.sent_message_ids:
                    continue
                author = msg.author.display_name
                uid = msg.author.id
                context_lines.append(f"[{author} (id:{uid})]: {msg.content}")
                new_msg_ids.append(msg.id)
            context_lines.reverse()
            new_msg_ids.reverse()
            context = "\n".join(context_lines) if context_lines else None
            log.info("  Collected %d new context messages (%d skipped as already sent)",
                     len(context_lines), CONTEXT_MESSAGE_COUNT - len(context_lines) - 1)

            # Remove the bot mention from the user's message
            user_text = message.content
            if self.user:
                user_text = user_text.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()

            display_name = message.author.display_name
            uid = message.author.id
            prompt = f"[{display_name} (id:{uid})]: {user_text}" if user_text else f"[{display_name} (id:{uid})] 提及了你"
            log.info("  Sending to Copilot: %s", prompt[:100])

            try:
                reply = await self.session_manager.send_message(
                    guild_id, channel_id, prompt, context
                )
                # Mark all context messages + current message as sent
                active.sent_message_ids.update(new_msg_ids)
                active.sent_message_ids.add(message.id)
                log.info("  Copilot replied (%d chars)", len(reply))
                for chunk in _chunk_message(reply):
                    await message.channel.send(chunk)
            except Exception:
                log.exception("Error processing message in #%s (guild=%d, channel=%d)", channel_name, guild_id, channel_id)
                await message.channel.send("⚠️ 處理訊息時發生錯誤，請稍後再試。")


def _ensure_copilot_auth() -> None:
    """Ensure the user is authenticated with Copilot CLI before starting."""
    cli = shutil.which("copilot")
    if not cli:
        log.error("Copilot CLI not found in PATH. Please install it first.")
        sys.exit(1)

    log.info("Checking Copilot CLI authentication...")

    # Quick check: run a trivial prompt to see if already authenticated.
    check = subprocess.run(
        [cli, "-p", "ok", "--allow-all-tools", "-s"],
        capture_output=True,
        timeout=30,
    )
    if check.returncode == 0:
        log.info("Copilot CLI authentication OK (already logged in).")
        return

    # Not authenticated — run interactive login with device flow.
    log.info("Not authenticated, starting login flow...")
    result = subprocess.run(
        [cli, "login"],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    if result.returncode != 0:
        log.error("Copilot CLI login failed (exit code %d).", result.returncode)
        sys.exit(1)
    log.info("Copilot CLI authentication OK.")


def run_bot() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    _ensure_copilot_auth()
    bot = TRPGBot()
    bot.run(DISCORD_TOKEN)
