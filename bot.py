import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

ALL_PAIRS_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
HISTORY_URL_TEMPLATE = "https://www.okx.com/priapi/v2/financial/market-lending-history?currencyId={}&pageSize=300&pageIndex=1"

CURRENCY_IDS = {
    "USDT": 7, "USDC": 283, "TON": 2054, "ZRO": 2425497, "APT": 2092, "BERA": 3197,
    "BETH": 1620, "ETHFI": 1215929, "CVC": 54, "CVX": 1911, "BABY": 3274, "IP": 3261,
    "KMNO": 1743707, "PARTI": 3185, "MAGIC": 1970, "PENGU": 3230, "SOPH": 3293,
    "XTZ": 1029, "DOT": 1486, "JST": 1438
}

SEARCH_INPUT = 1

_cached_assets = []

def fetch_all_pairs():
    global _cached_assets
    if _cached_assets:
        return _cached_assets
    try:
        resp = requests.get(ALL_PAIRS_URL)
        resp.raise_for_status()
        data = resp.json()
        assets = data.get("data", {}).get("list", [])
        if isinstance(assets, dict):
            assets = [assets]
        _cached_assets = assets
        return _cached_assets
    except Exception:
        return []

def fetch_history(currency_id):
    try:
        resp = requests.get(HISTORY_URL_TEMPLATE.format(currency_id))
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        if isinstance(items, dict):
            items = [items]
        return items
    except Exception:
        return []

def format_time_utc(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%H:%M UTC")

def format_datetime_utc(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M UTC")

def get_pair_data():
    assets = fetch_all_pairs()
    return [(a["currencyName"].upper(), a.get("preRate", 0), a.get("estimatedRate", 0), a.get("dateHour", 0)) for a in assets]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📋 View All Pairs", callback_data="view_pairs_0")],
        [InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
        [InlineKeyboardButton("📊 History", callback_data="history_menu_0")]
    ]
    await update.message.reply_text("Welcome! Please choose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

# ---- Search flow ----
async def search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the ticker you want to search (e.g., TON):")
    return SEARCH_INPUT

async def search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip().upper()
    assets = fetch_all_pairs()
    asset = next((a for a in assets if a["currencyName"].upper() == ticker), None)
    if not asset:
        await update.message.reply_text(f"Ticker {ticker} not found.")
        return ConversationHandler.END
    pre_rate = asset.get("preRate", 0) * 100
    est_rate = asset.get("estimatedRate", 0) * 100
    last_time = format_time_utc(asset.get("dateHour", 0))
    text = (
        f"♻ {ticker} Lending Rates at {last_time}\n\n"
        f"💰 Current rate: **{pre_rate:.2f}%**\n"
        f"📈 Predicted rate: **{est_rate:.2f}%**"
    )
    keyboard = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
         InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
        [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ---- View All Pairs pagination ----
async def view_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[2])
    pairs = get_pair_data()
    pairs.sort(key=lambda x: x[1], reverse=True)
    page_size = 10
    start_idx = page * page_size
    end_idx = start_idx + page_size
    pairs_page = pairs[start_idx:end_idx]
    text_lines = []
    for ticker, pre_rate, est_rate, date_hour in pairs_page:
        time_str = format_time_utc(date_hour)
        text_lines.append(f"{ticker} — **{pre_rate:.2f}%** ({time_str})")
    text = "📋 *All Pairs* (sorted by Current APR descending)\n\n" + "\n".join(text_lines)
    buttons = []
    if start_idx > 0:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"view_pairs_{page-1}"))
    if end_idx < len(pairs):
        buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"view_pairs_{page+1}"))
    keyboard = [[InlineKeyboardButton(t[0], callback_data=f"pair_{t[0]}")] for t in pairs_page]
    if buttons:
        keyboard.append(buttons)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ---- Show pair current+predicted rates ----
async def pair_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticker = query.data.split("_",1)[1].upper()
    assets = fetch_all_pairs()
    asset = next((a for a in assets if a["currencyName"].upper() == ticker), None)
    if not asset:
        await query.edit_message_text(f"Ticker {ticker} not found.")
        return
    pre_rate = asset.get("preRate", 0) * 100
    est_rate = asset.get("estimatedRate", 0) * 100
    last_time = format_time_utc(asset.get("dateHour", 0))
    text = (
        f"♻ {ticker} Lending Rates at {last_time}\n\n"
        f"💰 Current rate: **{pre_rate:.2f}%**\n"
        f"📈 Predicted rate: **{est_rate:.2f}%**"
    )
    keyboard = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
         InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
        [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ---- Refresh rate ----
async def refresh_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticker = query.data.split("_",1)[1].upper()
    assets = fetch_all_pairs()
    asset = next((a for a in assets if a["currencyName"].upper() == ticker), None)
    if not asset:
        await query.edit_message_text(f"Ticker {ticker} not found.")
        return
    pre_rate = asset.get("preRate", 0) * 100
    est_rate = asset.get("estimatedRate", 0) * 100
    last_time = format_time_utc(asset.get("dateHour", 0))
    text = (
        f"♻ {ticker} Lending Rates at {last_time}\n\n"
        f"💰 Current rate: **{pre_rate:.2f}%**\n"
        f"📈 Predicted rate: **{est_rate:.2f}%**"
    )
    keyboard = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
         InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
        [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ---- History menu pagination ----
async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[2])
    pairs = fetch_all_pairs()
    records = []
    for ticker, cid in CURRENCY_IDS.items():
        asset = next((a for a in pairs if a["currencyName"].upper() == ticker), None)
        if asset:
            apr = asset.get("preRate", 0) * 100
            dt_str = format_time_utc(asset.get("dateHour", 0))
            records.append((ticker, apr, dt_str))
    records.sort(key=lambda x: x[1], reverse=True)
    page_size = 10
    start_idx = page * page_size
    end_idx = start_idx + page_size
    chunk = records[start_idx:end_idx]
    text_lines = [f"{t} — **{a:.2f}%** ({dt})" for t,a,dt in chunk]
    text = "📊 *History — Latest APR by Pair*\n\n" + "\n".join(text_lines)
    buttons = []
    if start_idx > 0:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"history_menu_{page-1}"))
    if end_idx < len(records):
        buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"history_menu_{page+1}"))
    # Add "View All Pairs" button here for easy switch
    buttons.append(InlineKeyboardButton("📋 View All Pairs", callback_data="view_pairs_0"))
    keyboard = [[InlineKeyboardButton(t[0], callback_data=f"history_{t[0]}")] for t in chunk]
    keyboard.append(buttons)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ---- History detail ----
async def history_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticker = query.data.split("_",1)[1].upper()
    cid = CURRENCY_IDS.get(ticker)
    if not cid:
        await query.edit_message_text(f"Ticker {ticker} not supported for history.")
        return
    data = fetch_history(cid)
    if not data:
        await query.edit_message_text(f"No history data found for {ticker}.")
        return

    today_date = datetime.utcnow().date()
    rates_today = []
    lines = []
    for entry in data[:24]:
        apr = entry.get("rate", 0) * 100
        dt_str = format_datetime_utc(entry.get("dateHour", 0))
        rate_str = f"**{apr:.2f}%**" if apr >= 
