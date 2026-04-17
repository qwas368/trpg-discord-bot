"""Discord bot 核心：建立 bot 實例、註冊指令並處理頻道訊息。"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import (
    COPILOT_CONTEXT_MESSAGE_COUNT,
    DISCORD_TOKEN,
    GROK_CONTEXT_MESSAGE_COUNT,
)
from bot.copilot.session_manager import ActiveSession, SessionManager

log = logging.getLogger(__name__)

DISCORD_MAX_LENGTH = 2000


def _chunk_message(text: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """將長訊息切成 Discord 可接受的長度。"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # 優先在換行處切段，避免把一整句或格式區塊硬拆開。
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def _format_chat_line(author_name: str, author_id: int, content: str) -> str:
    """統一最近對話與 backfill 使用的訊息格式。"""
    return f"[{author_name} (id:{author_id})]: {content}"


def _strip_bot_mention(text: str, user: discord.ClientUser | None) -> str:
    """去掉 Discord mention，只保留玩家真正輸入的內容。"""
    if not user:
        return text.strip()
    return text.replace(f"<@{user.id}>", "").replace(f"<@!{user.id}>", "").strip()


def _resolve_bot_name(message: discord.Message, user: discord.ClientUser | None) -> str | None:
    """取得 bot 在目前 guild 內的顯示名稱，避免 prompt 裡叫錯名字。"""
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
    """濾掉 autocomplete 超時造成的雜訊錯誤。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and "autocomplete" in record.getMessage().lower():
            if record.exc_info and record.exc_info[1]:
                exc = record.exc_info[1]
                if isinstance(exc, discord.NotFound) and exc.code == 10062:
                    return False
        return True


class TRPGBot(commands.Bot):
    """TRPG bot 主體，負責 slash command 與 @mention 對話流程。"""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.session_manager = SessionManager()

        # Discord 的 autocomplete 只有短時間回應窗口，使用者快速切欄位時
        # 很容易出現 harmless 的 Unknown interaction；這裡直接過濾掉。
        _tree_logger = logging.getLogger("discord.app_commands.tree")
        _tree_logger.addFilter(_AutocompleteExpiredFilter())

    async def _collect_context_messages(
        self,
        channel: discord.abc.Messageable,
        before: discord.Message,
        active: ActiveSession,
        limit: int,
    ) -> list[discord.Message]:
        """收集某則訊息之前的 recent history，並依模式過濾不該重送的內容。"""
        messages: list[discord.Message] = []
        async for msg in channel.history(limit=limit, before=before):
            if active.mode == "copilot":
                # Copilot 模式下，避免把 bot 已經看過或待回補的訊息重複塞回去。
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
        """將 Grok 回覆送回 Discord，並順手記錄成未來回補 Copilot 的 transcript。"""
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

        # 全域處理 slash command interaction 過期的情況，避免 log 被洗滿。
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

        # 先清掉舊的 guild-specific 指令，避免不同版本 bot 殘留幽靈指令。
        for guild in self.guilds:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Cleared guild-specific commands for: %s", guild.name)

        # 再同步全域 slash commands。
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

        # 只有在被 @ 且該頻道有主持 session 時才接手處理。
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

            # Grok 與 Copilot 使用不同的 recent history 視窗大小。
            history_limit = (
                GROK_CONTEXT_MESSAGE_COUNT
                if active.mode == "grok"
                else COPILOT_CONTEXT_MESSAGE_COUNT
            )
            history_messages = await self._collect_context_messages(
                message.channel,
                message,
                active,
                history_limit,
            )
            context_lines = [
                _format_chat_line(msg.author.display_name, msg.author.id, msg.content)
                for msg in history_messages
            ]
            context = "\n".join(context_lines) if context_lines else None
            log.info(
                "  Collected %d context messages for %s mode (limit=%d)",
                len(context_lines),
                active.mode,
                history_limit,
            )

            # 把 mention 拿掉，避免模型把 <@123> 當成玩家真正內容。
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
                    # Grok 是 stateless，切回 Copilot 時需要靠這些 transcript 回補記憶。
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

                # Copilot SDK 的回覆是透過 session listener 推送；第一次收到訊息時才綁定 callback。
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
    """設定 logging、例外處理並啟動 Discord bot。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # 開啟低階錯誤 traceback，方便追像是 segfault 這種非一般 Python 例外。
    faulthandler.enable()

    # 捕捉背景 thread 的未處理例外，避免 reader thread 悄悄死掉。
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
