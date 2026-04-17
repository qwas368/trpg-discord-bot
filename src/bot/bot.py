"""Discord bot core — sets up the bot instance and message handling."""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import DISCORD_TOKEN
from bot.copilot.session_manager import ActiveSession, SessionManager

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


def _format_chat_line(author_name: str, author_id: int, content: str) -> str:
    return f"[{author_name} (id:{author_id})]: {content}"


def _strip_bot_mention(text: str, user: discord.ClientUser | None) -> str:
    if not user:
        return text.strip()
    return text.replace(f"<@{user.id}>", "").replace(f"<@!{user.id}>", "").strip()


def _resolve_bot_name(message: discord.Message, user: discord.ClientUser | None) -> str | None:
    if message.guild and user:
        member = message.guild.get_member(user.id)
        if member:
            return member.display_name
        if hasattr(message.guild, "me") and message.guild.me:
            return message.guild.me.display_name
    if user:
        return user.display_name
    return None


class _AutocompleteExpiredFilter(logging.Filter):
    """Suppress 'Unknown interaction' errors from autocomplete handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and "autocomplete" in record.getMessage().lower():
            if record.exc_info and record.exc_info[1]:
                exc = record.exc_info[1]
                if isinstance(exc, discord.NotFound) and exc.code == 10062:
                    return False
        return True


class TRPGBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.session_manager = SessionManager()

        # Suppress noisy "Unknown interaction" errors from autocomplete
        # These occur when Discord's 3-second timeout expires before the bot responds,
        # typically due to rapid field switching. Harmless and not actionable.
        _tree_logger = logging.getLogger("discord.app_commands.tree")
        _tree_logger.addFilter(_AutocompleteExpiredFilter())

    async def _collect_context_messages(
        self,
        channel: discord.abc.Messageable,
        before: discord.Message,
        active: ActiveSession,
    ) -> list[discord.Message]:
        messages: list[discord.Message] = []
        async for msg in channel.history(limit=CONTEXT_MESSAGE_COUNT, before=before):
            if active.mode == "copilot":
                if msg.id in active.sent_message_ids:
                    continue
                if active.pending_copilot_backfill and msg.id in active.grok_pending_message_ids:
                    continue
            messages.append(msg)
        messages.reverse()
        return messages

    async def _send_grok_reply(
        self,
        channel: discord.abc.Messageable,
        active: ActiveSession,
        reply: str,
    ) -> None:
        if not reply or not reply.strip():
            return

        for chunk in _chunk_message(reply):
            sent = await channel.send(chunk)
            active.record_grok_backfill(
                sent.id,
                _format_chat_line(sent.author.display_name, sent.author.id, chunk),
                sent.created_at,
            )

    async def setup_hook(self) -> None:
        await self.session_manager.start()
        await self.load_extension("bot.cogs.hosting")

        # Global error handler for expired interactions (code 10062)
        @self.tree.error
        async def on_app_command_error(
            interaction: discord.Interaction,
            error: app_commands.AppCommandError,
        ) -> None:
            if isinstance(error, app_commands.CommandInvokeError):
                original = error.original
                if isinstance(original, discord.NotFound) and original.code == 10062:
                    log.debug(
                        "Interaction expired for '/%s' (user=%s)",
                        interaction.command.name if interaction.command else "?",
                        interaction.user,
                    )
                    return
            log.error("Unhandled error in command '/%s'",
                      interaction.command.name if interaction.command else "?",
                      exc_info=error)

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

            history_messages = await self._collect_context_messages(message.channel, message, active)
            context_lines = [
                _format_chat_line(msg.author.display_name, msg.author.id, msg.content)
                for msg in history_messages
            ]
            context = "\n".join(context_lines) if context_lines else None
            log.info("  Collected %d context messages for %s mode", len(context_lines), active.mode)

            # Remove the bot mention from the user's message
            user_text = _strip_bot_mention(message.content, self.user)

            display_name = message.author.display_name
            uid = message.author.id
            prompt = (
                _format_chat_line(display_name, uid, user_text)
                if user_text
                else f"[{display_name} (id:{uid})] 提及了你"
            )

            try:
                if active.mode == "grok":
                    log.info("  Sending to Grok: %s", prompt[:100])
                    for history_message, context_line in zip(history_messages, context_lines):
                        active.record_grok_backfill(
                            history_message.id,
                            context_line,
                            history_message.created_at,
                        )
                    active.record_grok_backfill(message.id, prompt, message.created_at)
                    reply = await self.session_manager.send_grok_message(
                        guild_id,
                        channel_id,
                        prompt,
                        context,
                        _resolve_bot_name(message, self.user),
                    )
                    await self._send_grok_reply(message.channel, active, reply)
                    return

                # Set up the message callback to forward Copilot replies to this channel
                if not active._message_callback:
                    chan = message.channel

                    async def forward_to_discord(content: str) -> None:
                        if not content or not content.strip():
                            return
                        for chunk in _chunk_message(content):
                            await chan.send(chunk)

                    active.set_message_callback(forward_to_discord)

                log.info("  Sending to Copilot: %s", prompt[:100])
                fallback = await self.session_manager.send_message(guild_id, channel_id, prompt, context)
                active = self.session_manager.get_session(guild_id, channel_id) or active
                active.sent_message_ids.update(msg.id for msg in history_messages)
                active.sent_message_ids.add(message.id)
                if fallback:
                    await message.channel.send(fallback)
            except Exception:
                log.exception("Error processing message in #%s (guild=%d, channel=%d)", channel_name, guild_id, channel_id)
                await message.channel.send("⚠️ 處理訊息時發生錯誤，請稍後再試。")


def run_bot() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Enable faulthandler to print tracebacks on segfaults / aborts
    faulthandler.enable()

    # Catch unhandled exceptions in threads (e.g. Copilot SDK reader thread)
    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        log.error(
            "Unhandled exception in thread %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook

    bot = TRPGBot()
    try:
        bot.run(DISCORD_TOKEN)
    except Exception:
        log.exception("Bot crashed with unhandled exception")
        raise
    finally:
        log.info("Bot process exiting.")
