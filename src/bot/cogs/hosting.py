"""Slash commands for hosting TRPG sessions in Discord channels."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import DEFAULT_AI_MODEL
from bot.host_loader import list_hosts, list_models, load_host

log = logging.getLogger(__name__)

REASONING_EFFORTS = ["low", "medium", "high", "xhigh"]


def _resolve_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None,
) -> discord.TextChannel:
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        raise ValueError("請在文字頻道使用這個指令，或明確指定一個文字頻道。")
    return target


async def _host_type_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    try:
        hosts = list_hosts()
        return [
            app_commands.Choice(name=h, value=h)
            for h in hosts
            if current.lower() in h.lower()
        ][:25]
    except Exception:
        log.debug("autocomplete error for host_type", exc_info=True)
        return []


async def _model_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    try:
        models = list_models()
        return [
            app_commands.Choice(name=m, value=m)
            for m in models
            if current.lower() in m.lower()
        ][:25]
    except Exception:
        log.debug("autocomplete error for model", exc_info=True)
        return []


async def _ai_model_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    try:
        session_manager = getattr(interaction.client, "session_manager", None)
        if session_manager is None:
            models = [DEFAULT_AI_MODEL]
        else:
            models = await session_manager.get_available_models()
        return [
            app_commands.Choice(name=m, value=m)
            for m in models
            if current.lower() in m.lower()
        ][:25]
    except Exception:
        log.debug("autocomplete error for ai_model", exc_info=True)
        if current.lower() in DEFAULT_AI_MODEL.lower():
            return [app_commands.Choice(name=DEFAULT_AI_MODEL, value=DEFAULT_AI_MODEL)]
        return []


async def _reasoning_effort_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=effort, value=effort)
        for effort in REASONING_EFFORTS
        if current.lower() in effort.lower()
    ][:25]


class HostingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="host", description="在指定頻道開始主持 TRPG 遊戲")
    @app_commands.describe(
        channel="要主持的頻道",
        host_type="主持人類型 (如 coc, dnd)",
        model="遊戲模組 (可選)",
        ai_model="AI 模型 (可選，預設使用環境設定)",
        reasoning_effort="推理強度 (可選：low / medium / high / xhigh)",
    )
    @app_commands.autocomplete(
        host_type=_host_type_autocomplete,
        model=_model_autocomplete,
        ai_model=_ai_model_autocomplete,
        reasoning_effort=_reasoning_effort_autocomplete,
    )
    async def host(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        host_type: str,
        model: str | None = None,
        ai_model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        sm = self.bot.session_manager  # type: ignore[attr-defined]
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.response.send_message("此指令只能在伺服器中使用。", ephemeral=True)
            return

        if sm.is_hosting(guild_id, channel.id):
            log.warning("/host: already hosting in #%s (guild=%d)", channel.name, guild_id)
            await interaction.response.send_message(
                f"已經在 {channel.mention} 主持中了！請先使用 `/unhost` 離開。",
                ephemeral=True,
            )
            return

        # Validate host type
        try:
            host_config = load_host(host_type)
        except FileNotFoundError:
            log.error("/host: host type '%s' not found", host_type)
            available = ", ".join(list_hosts()) or "(無)"
            await interaction.response.send_message(
                f"找不到主持人類型 `{host_type}`。可用類型：{available}",
                ephemeral=True,
            )
            return

        if reasoning_effort and reasoning_effort not in REASONING_EFFORTS:
            await interaction.response.send_message(
                "找不到這個 reasoning effort。可用值：low, medium, high, xhigh",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        chosen_model = ai_model or DEFAULT_AI_MODEL
        log.info(
            "/host: user=%s channel=#%s host=%s ai_model=%s reasoning_effort=%s game_module=%s (guild=%d)",
            interaction.user.display_name,
            channel.name,
            host_type,
            chosen_model,
            reasoning_effort or "(default)",
            model or "(none)",
            guild_id,
        )

        try:
            # Try to resume first
            active = await sm.resume_session(
                guild_id, channel.id, host_config, chosen_model, reasoning_effort
            )
            if active:
                log.info("/host: resumed session in #%s (guild=%d)", channel.name, guild_id)
                parts = [
                    f"🎲 已恢復 {channel.mention} 的 **{host_type}** 遊戲！",
                    f"🤖 模型：`{active.ai_model}`",
                ]
                if active.reasoning_effort:
                    parts.append(f"🧠 推理強度：`{active.reasoning_effort}`")
                parts.append("在該頻道 @我 即可繼續遊戲。")
                await interaction.followup.send("\n".join(parts))
                return
        except Exception:
            log.debug("/host: resume failed for #%s, creating new session", channel.name, exc_info=True)

        try:
            active = await sm.create_session(
                guild_id, channel.id, host_config, chosen_model, model, reasoning_effort
            )
            log.info("/host: new session created in #%s (guild=%d)", channel.name, guild_id)
            parts = [
                f"🎲 開始在 {channel.mention} 主持 **{host_type}** TRPG！",
                f"🤖 模型：`{active.ai_model}`",
            ]
            if active.reasoning_effort:
                parts.append(f"🧠 推理強度：`{active.reasoning_effort}`")
            if model:
                parts.append(f"📜 遊戲模組：`{model}`")
            parts.append("在該頻道 @我 即可開始遊戲。")
            await interaction.followup.send("\n".join(parts))
        except Exception:
            log.exception("/host: failed to create session in #%s (guild=%d)", channel.name, guild_id)
            await interaction.followup.send("⚠️ 建立遊戲 session 失敗，請稍後再試。")

    @app_commands.command(name="grok", description="切換指定頻道的 Grok 模式")
    @app_commands.describe(channel="要切換模式的頻道 (預設目前頻道)")
    async def grok(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        sm = self.bot.session_manager  # type: ignore[attr-defined]
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.response.send_message("此指令只能在伺服器中使用。", ephemeral=True)
            return

        try:
            target_channel = _resolve_channel(interaction, channel)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        if not sm.is_hosting(guild_id, target_channel.id):
            await interaction.response.send_message(
                f"目前沒有在 {target_channel.mention} 主持，請先使用 `/host`。",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            active, enabled = sm.toggle_grok_mode(guild_id, target_channel.id)
        except RuntimeError as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return

        if enabled:
            parts = [
                f"⚡ 已切換 {target_channel.mention} 到 **Grok** 模式。",
                f"🤖 Grok 模型：`{active.grok_model}`",
                "🧠 之後每次 @我，都會用最近 20 筆 Discord 對話重建上下文。",
            ]
        else:
            parts = [f"🔁 已切回 {target_channel.mention} 的 **Copilot** 模式。"]
            if active.grok_pending_lines:
                parts.append(
                    "📝 下次在該頻道 @我 時，會先把 Grok 模式期間未同步的對話補回 Copilot。"
                )
            else:
                parts.append("📝 這次沒有需要回補給 Copilot 的 Grok 對話。")
            parts.append(f"🤖 Copilot 模型：`{active.ai_model}`")
        await interaction.followup.send("\n".join(parts))

    @app_commands.command(name="status", description="查看指定頻道目前的主持狀態")
    @app_commands.describe(channel="要查看的頻道 (預設目前頻道)")
    async def status(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        sm = self.bot.session_manager  # type: ignore[attr-defined]
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.response.send_message("此指令只能在伺服器中使用。", ephemeral=True)
            return

        try:
            target_channel = _resolve_channel(interaction, channel)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        if not sm.is_hosting(guild_id, target_channel.id):
            await interaction.response.send_message(
                f"目前沒有在 {target_channel.mention} 主持。",
                ephemeral=True,
            )
            return

        active = sm.require_session(guild_id, target_channel.id)
        parts = [
            f"🎲 {target_channel.mention} 目前主持中",
            f"🧭 模式：`{active.mode}`",
            f"🤖 Copilot 模型：`{active.ai_model}`",
            f"⚡ Grok 模型：`{active.grok_model}`",
        ]
        if active.reasoning_effort:
            parts.append(f"🧠 Copilot 推理強度：`{active.reasoning_effort}`")
        if active.mode == "grok":
            parts.append("📚 Grok 會在每次 @我 時重建最近 20 筆 Discord 上下文。")
        if active.pending_copilot_backfill:
            parts.append(f"📝 待同步 Grok 訊息：`{len(active.grok_pending_lines)}`")
        await interaction.response.send_message("\n".join(parts))

    @app_commands.command(name="unhost", description="離開指定頻道的 TRPG 主持")
    @app_commands.describe(channel="要離開的頻道")
    async def unhost(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        sm = self.bot.session_manager  # type: ignore[attr-defined]
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.response.send_message("此指令只能在伺服器中使用。", ephemeral=True)
            return

        if not sm.is_hosting(guild_id, channel.id):
            log.warning("/unhost: not hosting in #%s (guild=%d)", channel.name, guild_id)
            await interaction.response.send_message(
                f"目前沒有在 {channel.mention} 主持。", ephemeral=True
            )
            return

        await interaction.response.defer()
        await sm.close_session(guild_id, channel.id)
        log.info("/unhost: stopped hosting #%s (guild=%d, user=%s)", channel.name, guild_id, interaction.user.display_name)
        await interaction.followup.send(
            f"👋 已離開 {channel.mention} 的主持。遊戲進度已保存，可用 `/host` 恢復。"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HostingCog(bot))
