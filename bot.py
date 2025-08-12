import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

# API Endpoints
ALL_PAIRS_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
HISTORY_URL_TEMPLATE = "https://www.okx.com/priapi/v2/financial/market-lending-history?currencyId={}&pageSize=300&pageIndex=1"

# Supported history tickers
CURRENCY_IDS = {
    "USDT": 7, "USDC": 283, "TON": 2054, "ZRO": 2425497, "APT": 2092, "BERA": 3197,
    "BETH": 1620, "ETHFI": 1215929, "CVC": 54, "CVX": 1911, "BABY": 3274, "IP": 3261,
    "KMNO": 1743707, "PARTI": 3185, "MAGIC": 1970, "PENGU": 3230, "SOPH": 3293,
    "XTZ": 1029, "DOT": 1486, "JST": 1438
}

# Helper functions
def fetch_all_pairs():
    resp = requests.get(ALL_PAIRS_URL)
    data = resp.json()
    if "data" not in data or "list" not in data["data"]:
        return []
    return data["data"]["list"]

def fetch_history(currency_id):
    resp = requests.get(HISTORY_URL_TEMPLATE.format(currency_id))
    data = resp.json()
    if "data" not in data or "list" not in data["data"]:
        return []
    return data["data"]["list"]

def format_time_utc(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%H:%M UTC")

def format_datetime_utc(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M UTC")

# Telegram bot commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📋 View All Pairs", callback_data="view_pairs_0")],
        [InlineKeyboardButton("🔍 Search", callback_data="search")],
        [InlineKeyboardButton("📊 History", callback_data="history_menu_0")]
    ]
    await update.message.reply_text("Welcome! Please choose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    pairs = fetch_all_pairs()
    pairs_sorted = sorted(pairs, key=lambda x: x.get("preRate", 0), reverse=True)
    page_size = 10
    start_idx = page * page_size
    end_idx = start_idx + page_size
    text_lines = []
    for item in pairs_sorted[start_idx:end_idx]:
        ticker = item["currencyName"].upper()
        apr = item["preRate"] * 100
        time_str = format_time_utc(item["dateHour"])
        text_lines.append(f"{ticker} — **{apr:.2f}%** ({time_str})")
    text = "📋 *All Pairs* (sorted by APR)\n\n" + "\n".join(text_lines)
    buttons = []
    if start_idx > 0:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"view_pairs_{page-1}"))
    if end_idx < len(pairs_sorted):
        buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"view_pairs_{page+1}"))
    keyboard = [buttons] if buttons else []
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Enter ticker (e.g., TON):")
    context.user_data["awaiting_search"] = True

async def handle_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_search"):
        ticker = update.message.text.strip().upper()
        pairs = fetch_all_pairs()
        item = next((p for p in pairs if p["currencyName"].upper() == ticker), None)
        if item:
            apr = item["preRate"] * 100
            time_str = format_time_utc(item["dateHour"])
            text = f"♻ {ticker} Lending Rates at {time_str}\n\nCurrent APR: **{apr:.2f}%**"
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"Ticker {ticker} not found.")
        context.user_data["awaiting_search"] = False

async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    records = []
    pairs = fetch_all_pairs()
    for ticker, cid in CURRENCY_IDS.items():
        item = next((p for p in pairs if p["currencyName"].upper() == ticker), None)
        if item:
            apr = item["preRate"] * 100
            time_str = format_time_utc(item["dateHour"])
            records.append((ticker, apr, time_str))
    records.sort(key=lambda x: x[1], reverse=True)
    page_size = 10
    start_idx = page * page_size
    end_idx = start_idx + page_size
    text_lines = [f"{t} — **{a:.2f}%** ({ts})" for t, a, ts in records[start_idx:end_idx]]
    text = "📊 *History — Latest APR by Pair*\n\n" + "\n".join(text_lines)
    buttons = []
    if start_idx > 0:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"history_menu_{page-1}"))
    if end_idx < len(records):
        buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"history_menu_{page+1}"))
    keyboard = [[InlineKeyboardButton(t, callback_data=f"history_{t}")] for t, _, _ in records[start_idx:end_idx]]
    if buttons:
        keyboard.append(buttons)
    await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def history_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker):
    cid = CURRENCY_IDS[ticker]
    data = fetch_history(cid)
    if not data:
        await update.callback_query.message.reply_text(f"Failed to fetch history for {ticker}.")
        return
    today = datetime.utcnow().strftime("%Y-%m-%d")
    today_rates = []
    lines = []
    for item in data[:24]:
        apr = item["rate"] * 100
        time_str = format_datetime_utc(item["dateHour"])
        rate_str = f"**{apr:.2f}%**" if apr >= 20 else f"{apr:.2f}%"
        lines.append(f"{time_str} — {rate_str}")
        if today in time_str:
            today_rates.append(apr)
    avg_today = sum(today_rates) / len(today_rates) if today_rates else 0
    text = f"{ticker} Lending Rate — Last 24 records\n\n📌 Average APR for {today} (UTC): {avg_today:.2f}%\n\n" + "\n".join(lines)
    await update.callback_query.message.reply_text(text, parse_mode="Markdown")

# Handlers
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("view_pairs_"):
        page = int(query.data.split("_")[2])
        await view_pairs(update, context, page)
    elif query.data == "search":
        await search(update, context)
    elif query.data.startswith("history_menu_"):
        page = int(query.data.split("_")[2])
        await history_menu(update, context, page)
    elif query.data.startswith("history_"):
        ticker = query.data.split("_")[1]
        await history_detail(update, context, ticker)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_input))
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
