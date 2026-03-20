"""Slash commands for hosting TRPG sessions in Discord channels."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.host_loader import list_hosts, list_models, load_host

log = logging.getLogger(__name__)

AI_MODELS = [
    "claude-sonnet-4.6",
    "claude-sonnet-4.5",
    "claude-opus-4.6",
    "claude-opus-4.5",
    "gpt-5",
    "gpt-5.1",
    "gpt-5.2",
    "gpt-4.1",
    "gemini-3-pro-preview",
]


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
    return [
        app_commands.Choice(name=m, value=m)
        for m in AI_MODELS
        if current.lower() in m.lower()
    ][:25]


class HostingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="host", description="在指定頻道開始主持 TRPG 遊戲")
    @app_commands.describe(
        channel="要主持的頻道",
        host_type="主持人類型 (如 coc, dnd)",
        model="遊戲模組 (可選)",
        ai_model="AI 模型 (預設 claude-sonnet-4.6)",
    )
    @app_commands.autocomplete(
        host_type=_host_type_autocomplete,
        model=_model_autocomplete,
        ai_model=_ai_model_autocomplete,
    )
    async def host(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        host_type: str,
        model: str | None = None,
        ai_model: str | None = None,
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

        await interaction.response.defer()

        chosen_model = ai_model or "claude-sonnet-4.6"
        log.info(
            "/host: user=%s channel=#%s host=%s ai_model=%s game_module=%s (guild=%d)",
            interaction.user.display_name, channel.name, host_type, chosen_model, model or "(none)", guild_id,
        )

        try:
            # Try to resume first
            active = await sm.resume_session(guild_id, channel.id, host_config, chosen_model)
            if active:
                log.info("/host: resumed session in #%s (guild=%d)", channel.name, guild_id)
                await interaction.followup.send(
                    f"🎲 已恢復 {channel.mention} 的 **{host_type}** 遊戲！\n"
                    f"🤖 模型：`{chosen_model}`\n"
                    f"在該頻道 @我 即可繼續遊戲。"
                )
                return
        except Exception:
            log.debug("/host: resume failed for #%s, creating new session", channel.name, exc_info=True)

        try:
            await sm.create_session(
                guild_id, channel.id, host_config, chosen_model, model
            )
            log.info("/host: new session created in #%s (guild=%d)", channel.name, guild_id)
            parts = [
                f"🎲 開始在 {channel.mention} 主持 **{host_type}** TRPG！",
                f"🤖 模型：`{chosen_model}`",
            ]
            if model:
                parts.append(f"📜 遊戲模組：`{model}`")
            parts.append("在該頻道 @我 即可開始遊戲。")
            await interaction.followup.send("\n".join(parts))
        except Exception:
            log.exception("/host: failed to create session in #%s (guild=%d)", channel.name, guild_id)
            await interaction.followup.send("⚠️ 建立遊戲 session 失敗，請稍後再試。")

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
