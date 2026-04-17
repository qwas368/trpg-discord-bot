# TRPG Discord Bot

A Discord bot that acts as a TRPG Game Master (GM/Keeper), powered by GitHub Copilot SDK.

## Features

- 🎲 支援多種 TRPG 系統 (CoC, D&D...) — 透過 `hosts/` 資料夾切換
- 📺 多頻道同時主持，每個頻道獨立 session
- 💾 遊戲進度持久化，支援跨重啟恢復
- 🤖 可選擇 AI 模型
- 🧠 可設定 reasoning effort
- 📜 可載入遊戲模組 (`models/` 資料夾)

## Setup

1. Install dependencies:
   ```bash
   pip install -e .
   ```

2. Copy `.env.example` to `.env` and fill in your Discord bot token:
   ```bash
   cp .env.example .env
   ```
   If you want to use `/grok`, also fill in `XAI_API_KEY`.

3. Ensure GitHub Copilot CLI is installed and you are logged in:
   ```bash
   copilot --version
   ```

4. Run the bot:
   ```bash
   trpg-bot
   # or
   python -m bot.main
   ```

## Commands

| Command | Description |
|---------|-------------|
| `/host [channel] [host_type] [model] [ai_model] [reasoning_effort]` | 在指定頻道開始主持 TRPG |
| `/grok [channel]` | 切換指定頻道的 Grok 模式，並先用最近 50 則訊息產生角色摘要 |
| `/status [channel]` | 查看指定頻道目前使用 Grok 或 Copilot |
| `/unhost [channel]` | 離開指定頻道的主持 |

## Project Structure

```
hosts/          — TRPG 主持人設定 (.github 格式)
models/         — 遊戲模組 (.txt, .md, .json)
src/bot/        — Bot 原始碼
```
