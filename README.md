# TRPG Discord Bot

A Discord bot that acts as a TRPG Game Master (GM/Keeper), powered by GitHub Copilot SDK.

## Features

- 🎲 支援多種 TRPG 系統 (CoC, D&D...) — 透過 `hosts/` 資料夾切換
- 📺 多頻道同時主持，每個頻道獨立 session
- 💾 遊戲進度持久化，支援跨重啟恢復
- 🤖 可選擇 AI 模型
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
| `/host [channel] [host_type] [model] [ai_model]` | 在指定頻道開始主持 TRPG |
| `/leave [channel]` | 離開指定頻道的主持 |

## Project Structure

```
hosts/          — TRPG 主持人設定 (.github 格式)
models/         — 遊戲模組 (.txt, .md, .json)
src/bot/        — Bot 原始碼
```
