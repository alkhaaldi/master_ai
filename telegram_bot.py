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
        "/lights - \u062D\u0627\u0644\u0629 \u0627\u0644\u0623\u0646\u0648\u0627\u0631\n"\n        "/events - \u0622\u062E\u0631 \u0627\u0644\u0623\u062D\u062F\u0627\u062B\n"\n        "/approve - \u0645\u0648\u0627\u0641\u0642\u0629 \u0639\u0644\u0649 \u062D\u062F\u062B\n"\n        "/autonomy - \u0625\u0639\u062F\u0627\u062F\u0627\u062A \u0627\u0644\u0627\u0633\u062A\u0642\u0644\u0627\u0644\u064A\u0629\n"\n        "/policy - \u0633\u064A\u0627\u0633\u0629 \u0627\u0644\u0645\u062E\u0627\u0637\u0631\n\n"
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


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    data = await call_master("/events?limit=10")
    if "error" in data:
        await update.message.reply_text("\u274c " + data["error"])
        return
    events = data.get("events", [])
    if not events:
        await update.message.reply_text("\u2705 \u0645\u0627 \u0641\u064a \u0623\u062d\u062f\u0627\u062b")
        return
    lines = ["\U0001F4CB \u0622\u062e\u0631 10 \u0623\u062d\u062f\u0627\u062b:\n"]
    for ev in events:
        risk_icon = {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U0001F7E2"}.get(ev.get("risk",""), "\u26AA")
        status_icon = {"completed": "\u2705", "waiting_approval": "\u23F3", "pending": "\u23F1", "error": "\u274c"}.get(ev.get("status",""), "\u2753")
        score = ev.get("risk_score", "?")
        lines.append(f"{risk_icon}{status_icon} [{ev.get('type','')}] {ev.get('title','')} (score:{score})")
        lines.append(f"   ID: {ev.get('event_id','')} | {ev.get('created_at','')}")
    await send_long(update.message, "\n".join(lines))

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    args = context.args
    if not args:
        # Show waiting events
        data = await call_master("/events?limit=20")
        events = data.get("events", [])
        waiting = [e for e in events if e.get("status") == "waiting_approval"]
        if not waiting:
            await update.message.reply_text("\u2705 \u0645\u0627 \u0641\u064a \u0623\u062d\u062f\u0627\u062b \u062a\u0646\u062a\u0638\u0631 \u0645\u0648\u0627\u0641\u0642\u0629")
            return
        lines = ["\u23F3 \u0623\u062d\u062f\u0627\u062b \u062a\u0646\u062a\u0638\u0631 \u0645\u0648\u0627\u0641\u0642\u0629:\n"]
        for ev in waiting:
            lines.append(f"\U0001F534 [{ev.get('type','')}] {ev.get('title','')}")
            lines.append(f"   /approve {ev.get('event_id','')}")
        await send_long(update.message, "\n".join(lines))
        return
    eid = args[0]
    action = args[1] if len(args) > 1 else "approve"
    result = await call_master(f"/events/{eid}/approve?action={action}", method="POST")
    if "error" in result:
        await update.message.reply_text(f"\u274c {result['error']}")
    else:
        await update.message.reply_text(f"\u2705 {result.get('status', 'done')} - {eid}")

async def cmd_autonomy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    args = context.args
    if not args:
        cfg = await call_master("/autonomy/config")
        enabled = "\u2705" if cfg.get("enabled") else "\u274c"
        await update.message.reply_text(
            f"\u2699\uFE0F Autonomy Config:\n\n"
            f"Enabled: {enabled}\n"
            f"Level: {cfg.get('level', '?')}/5\n"
            f"Allow Medium: {cfg.get('allow_medium', False)}\n"
            f"Allow High: {cfg.get('allow_high', False)}\n\n"
            f"\u062A\u063A\u064A\u064A\u0631: /autonomy <level> (1-5)"
        )
        return
    try:
        level = int(args[0])
        result = await call_master("/autonomy/config", method="POST", data={"enabled": True, "level": level, "allow_medium": level >= 4, "allow_high": level >= 5})
        cfg = result.get("config", result)
        await update.message.reply_text(f"\u2705 Autonomy level: {cfg.get('level', level)}/5")
    except ValueError:
        await update.message.reply_text("\u274c \u0627\u0633\u062A\u062E\u062F\u0645: /autonomy 3")

async def cmd_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    policy = await call_master("/policy")
    t = policy.get("thresholds", {})
    await update.message.reply_text(
        f"\U0001F4DC Policy v{policy.get('version', '?')}:\n\n"
        f"Auto (score 0-{t.get('auto_max', '?')}): \u2705 \u062A\u0646\u0641\u064A\u0630 \u062A\u0644\u0642\u0627\u0626\u064A\n"
        f"Approval (score {t.get('auto_max',25)+1}-{t.get('approval_max', '?')}): \u23F3 \u064A\u0646\u062A\u0638\u0631 \u0645\u0648\u0627\u0641\u0642\u0629\n"
        f"Block (score {t.get('block_min', '?')}+): \U0001F6AB \u0645\u0645\u0646\u0648\u0639"
    )

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
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("autonomy", cmd_autonomy))
    app.add_handler(CommandHandler("policy", cmd_policy))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
