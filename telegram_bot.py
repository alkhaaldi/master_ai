#!/usr/bin/env python3
"""Master AI Telegram Bot - Direct interface to Master AI"""

import os
import sys
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Config ---
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MASTER_AI_URL = "http://localhost:9000"
MASTER_AI_KEY = os.getenv("MASTER_AI_API_KEY", "")
ALLOWED_USERS = set()  # Will be populated on first /start

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tg_bot")


async def send_long(msg, text):
    MAX = 4000
    if len(text) <= MAX:
        await msg.reply_text(text)
        return
    while text:
        if len(text) <= MAX:
            await msg.reply_text(text)
            break
        idx = text[:MAX].rfind(chr(10))
        if idx < 100:
            idx = MAX
        await msg.reply_text(text[:idx])
        text = text[idx:].lstrip(chr(10))

# --- Helper: Call Master AI ---
async def call_master(endpoint, method="GET", data=None):
    headers = {"X-API-Key": MASTER_AI_KEY, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{MASTER_AI_URL}{endpoint}"
            if method == "GET":
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    return await r.json()
            else:
                async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    return await r.json()
    except Exception as e:
        logger.error("Master AI call failed: %s", e)
        return {"error": str(e)}

# --- Security: Check if user is allowed ---
def is_allowed(user_id):
    if not ALLOWED_USERS:
        return True  # First user auto-allowed
    return user_id in ALLOWED_USERS

# --- Commands ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    ALLOWED_USERS.add(uid)
    # Save user's telegram ID
    logger.info("User registered: %s (id: %d)", user.first_name, uid)
    
    await update.message.reply_text(
        f"\u0623\u0647\u0644\u0627\u064b {user.first_name}! \U0001F44B\n\n"
        f"\u0623\u0646\u0627 Master AI - \u0645\u0633\u0627\u0639\u062F\u0643 \u0627\u0644\u0630\u0643\u064A \U0001F3E0\n\n"
        f"\u0627\u0631\u0633\u0644 \u0644\u064A \u0623\u064A \u0623\u0645\u0631 \u0648\u0623\u0646\u0627 \u0623\u0646\u0641\u0630\u0647!\n\n"
        f"/help - \u0627\u0644\u0623\u0648\u0627\u0645\u0631\n"
        f"/status - \u062D\u0627\u0644\u0629 \u0627\u0644\u0646\u0638\u0627\u0645"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001F4CB \u0627\u0644\u0623\u0648\u0627\u0645\u0631:\n\n"
        "/status - \u062D\u0627\u0644\u0629 \u0627\u0644\u0646\u0638\u0627\u0645\n"
        "/tasks - \u0627\u0644\u0645\u0647\u0627\u0645\n"
        "/memory - \u0625\u062D\u0635\u0627\u0626\u064A\u0627\u062A \u0627\u0644\u0630\u0627\u0643\u0631\u0629\n"
        "/lights - \u062D\u0627\u0644\u0629 \u0627\u0644\u0623\u0646\u0648\u0627\u0631\n\n"
        "\u0623\u0648 \u0627\u0631\u0633\u0644 \u0623\u064A \u0631\u0633\u0627\u0644\u0629 \u0648\u0623\u0646\u0627 \u0623\u0641\u0647\u0645\u0647\u0627 \U0001F9E0"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    health = await call_master("/health")
    mem_stats = await call_master("/memory/stats")
    
    if "error" in health:
        await update.message.reply_text("\u274C Master AI \u0645\u0648 \u0634\u063A\u0627\u0644!")
        return
    
    text = (
        f"\u2705 Master AI {health.get('version', '?')}\n"
        f"\U0001F9E0 \u0630\u0627\u0643\u0631\u0629: {mem_stats.get('total', 0)} \u0630\u0643\u0631\u0649\n"
        f"\U0001F4BB Agents: {len(health.get('agents', []))}\n"
        f"\U0001F4CB Jobs: {health.get('queued_jobs', 0)}"
    )
    await update.message.reply_text(text)

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await call_master("/tasks/summary")
    if "error" in data:
        await update.message.reply_text("\u274C \u0645\u0627 \u0642\u062F\u0631\u062A \u0623\u062C\u064A\u0628 \u0627\u0644\u0645\u0647\u0627\u0645")
        return
    
    total = data.get("total", 0)
    pending = data.get("pending", 0)
    urgent = data.get("urgent_tasks", [])
    
    text = f"\U0001F4CB \u0627\u0644\u0645\u0647\u0627\u0645: {total} ({pending} \u0645\u0639\u0644\u0642\u0629)\n"
    if urgent:
        text += "\n\u26A0\uFE0F \u0639\u0627\u062C\u0644\u0629:\n"
        for t in urgent[:5]:
            text += f"  \u2022 {t.get('title', '?')}\n"
    
    await update.message.reply_text(text)

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await call_master("/memory/stats")
    if "error" in stats:
        await update.message.reply_text("\u274C")
        return
    
    text = (
        f"\U0001F9E0 \u0627\u0644\u0630\u0627\u0643\u0631\u0629:\n"
        f"\u0627\u0644\u0645\u062C\u0645\u0648\u0639: {stats.get('total', 0)}\n"
    )
    by_cat = stats.get("by_category", {})
    for cat, count in by_cat.items():
        text += f"  {cat}: {count}\n"
    
    await update.message.reply_text(text)

# --- Main message handler: Send to /agent ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("\u26D4 \u063A\u064A\u0631 \u0645\u0635\u0631\u062D")
        return
    
    user_text = update.message.text
    if not user_text:
        return
    
    # Show typing
    await update.message.chat.send_action("typing")
    
    # Send to /agent
    result = await call_master("/agent", method="POST", data={"task": user_text})
    
    # If agent failed or could not plan, fallback to /ask (conversational)
    summary = result.get("summary", "")
    if "Could not plan" in summary or "could not plan" in summary.lower():
        ask_result = await call_master("/ask", method="POST", data={"prompt": user_text})
        if "response" in ask_result:
            await send_long(update.message, ask_result["response"])
            return
    
    if "error" in result:
        await update.message.reply_text(f"\u274C \u062E\u0637\u0623: {result['error']}")
        return
    
    summary = result.get("summary", "\u062A\u0645")
    needs_approval = result.get("needs_approval", False)
    approval_id = result.get("approval_id")
    
    if needs_approval and approval_id:
        actions_text = ""
        for a in result.get("actions", []):
            actions_text += f"  \u2022 {a.get('type')}: {a.get('why', '')}\n"
        await update.message.reply_text(
            f"\u26A0\uFE0F \u064A\u0628\u064A \u0645\u0648\u0627\u0641\u0642\u0629:\n{actions_text}\n"
            f"\u0627\u0631\u0633\u0644: /approve_{approval_id}"
        )
    else:
        await update.message.reply_text(summary)

# --- Main ---
async def post_init(application):
    commands = [
        BotCommand("start", "\u0628\u062F\u0627\u064A\u0629"),
        BotCommand("help", "\u0645\u0633\u0627\u0639\u062F\u0629"),
        BotCommand("status", "\u062D\u0627\u0644\u0629 \u0627\u0644\u0646\u0638\u0627\u0645"),
        BotCommand("tasks", "\u0627\u0644\u0645\u0647\u0627\u0645"),
        BotCommand("memory", "\u0627\u0644\u0630\u0627\u0643\u0631\u0629"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set")

def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)
    
    logger.info("Starting Telegram Bot...")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
