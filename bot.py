# bot.py
import os
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# -------------------------
# Config + logging
# -------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("okx_rate_bot")

# -------------------------
# Constants
# -------------------------
ALL_PAIRS_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
HISTORY_URL_TEMPLATE = "https://www.okx.com/priapi/v2/financial/market-lending-history?currencyId={}&pageSize=300&pageIndex=1"

CURRENCY_IDS = {
    "USDT": 7, "USDC": 283, "TON": 2054, "ZRO": 2425497, "APT": 2092, "BERA": 3197,
    "BETH": 1620, "ETHFI": 1215929, "CVC": 54, "CVX": 1911, "BABY": 3274, "IP": 3261,
    "KMNO": 1743707, "PARTI": 3185, "MAGIC": 1970, "PENGU": 3230, "SOPH": 3293,
    "XTZ": 1029, "DOT": 1486, "JST": 1438
}

# Conversation states
SEARCH_INPUT = 1
PAIRS_FILTER_INPUT = 2

# Pagination
PAGE_SIZE = 10

# Simple cache to avoid hitting API too often (time in seconds)
_cache = {
    "assets": {"ts": 0, "data": []},
}
CACHE_TTL = 30  # seconds

# -------------------------
# Helpers: API + formatting
# -------------------------
def fetch_assets(force: bool = False) -> List[Dict[str, Any]]:
    """Fetch (and cache) market-lending-info list."""
    now = time.time()
    if not force and _cache["assets"]["data"] and (now - _cache["assets"]["ts"] < CACHE_TTL):
        return _cache["assets"]["data"]

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        logger.info("Fetching market-lending-info from OKX")
        r = requests.get(ALL_PAIRS_URL, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", {}).get("list", [])
        if isinstance(items, dict):
            items = [items]
        _cache["assets"]["data"] = items
        _cache["assets"]["ts"] = now
        logger.info("Assets fetched: %d", len(items))
        return items
    except Exception as e:
        logger.exception("Failed to fetch assets: %s", e)
        return _cache["assets"]["data"] or []

def find_asset_by_ticker(ticker: str, assets: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    if assets is None:
        assets = fetch_assets()
    ticker = ticker.upper()
    for a in assets:
        name = (a.get("currencyName") or "").upper()
        if name == ticker:
            return a
    return None

def fetch_history_entries(currency_id: int) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    url = HISTORY_URL_TEMPLATE.format(currency_id)
    try:
        logger.info("Fetching history for currencyId=%s", currency_id)
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", {}).get("list", [])
        if isinstance(items, dict):
            items = [items]
        logger.info("History entries: %d", len(items))
        return items
    except Exception as e:
        logger.exception("Failed to fetch history for %s: %s", currency_id, e)
        return []

def ms_to_utc_time(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%H:%M UTC")
    except Exception:
        return "N/A"

def ms_to_utc_dt(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "N/A"

def safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0

# -------------------------
# UI builders
# -------------------------
def build_paginated_keyboard(items: List[str], page: int, prefix: str) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    chunk = items[start:start + PAGE_SIZE]
    keyboard = [[InlineKeyboardButton(t, callback_data=f"{prefix}_item_{t}")] for t in chunk]
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"{prefix}_page_{page-1}"))
    if start + PAGE_SIZE < len(items):
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"{prefix}_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    # add handy buttons
    keyboard.append([
        InlineKeyboardButton("🔍 Search Pairs", callback_data="pairs_search"),
        InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")
    ])
    return InlineKeyboardMarkup(keyboard)

def build_history_menu_keyboard(records: List[tuple], page: int) -> InlineKeyboardMarkup:
    # records: list of (ticker, apr_float, hhmm)
    start = page * PAGE_SIZE
    chunk = records[start:start + PAGE_SIZE]
    keyboard = [[InlineKeyboardButton(f"{t} — {apr:.2f}% ({hh})", callback_data=f"history_item_{t}")] for t, apr, hh in chunk]
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"history_page_{page-1}"))
    if start + PAGE_SIZE < len(records):
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"history_page_{page+1}"))
    # add view all pairs / back menu
    nav.append(InlineKeyboardButton("📋 View All Pairs", callback_data="pairs_page_0"))
    keyboard.append(nav)
    return InlineKeyboardMarkup(keyboard)

# -------------------------
# Handlers
# -------------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info("User %s started bot", user.id if user else "unknown")
    kb = [
        [InlineKeyboardButton("📋 View All Pairs", callback_data="pairs_page_0")],
        [InlineKeyboardButton("🔍 Search (ticker)", callback_data="search_prompt")],
        [InlineKeyboardButton("📊 History", callback_data="history_page_0")],
    ]
    await update.message.reply_text("Welcome — choose an option:", reply_markup=InlineKeyboardMarkup(kb))

# ---- Search conversation ----
async def search_prompt_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_search"] = True
    logger.info("User %s prompted to search ticker", update.effective_user.id)
    await query.edit_message_text("Enter ticker (e.g. TON):")
    return SEARCH_INPUT

async def search_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    context.user_data["awaiting_search"] = False
    logger.info("User %s searching ticker %s", update.effective_user.id, text)
    assets = fetch_assets(force=True)
    asset = find_asset_by_ticker(text, assets)
    if not asset:
        await update.message.reply_text(f"❌ Ticker {text} not found.")
        return ConversationHandler.END

    pre = safe_float(asset.get("preRate", 0)) * 100
    est = safe_float(asset.get("estimatedRate", 0)) * 100
    ts = asset.get("dateHour") or asset.get("dateHourStr")
    # prefer numeric ms timestamp
    last_time = ms_to_utc_dt(asset.get("dateHour")) if asset.get("dateHour") else "N/A"
    msg = (
        f"♻ {text} Lending Rates at {last_time}\n"
        f"💰 Current rate: {pre:.2f}%\n"
        f"📈 Predicted rate: {est:.2f}%"
    )
    kb = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{text}"),
         InlineKeyboardButton("📊 History", callback_data=f"history_item_{text}")],
        [InlineKeyboardButton("📋 View All Pairs", callback_data="pairs_page_0")]
    ]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ---- View All Pairs ----
async def pairs_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # callback format pairs_page_{n}
    try:
        page = int(query.data.split("_")[-1])
    except Exception:
        page = 0
    assets = fetch_assets()
    # create sorted tickers by preRate descending
    pairs = []
    for a in assets:
        name = (a.get("currencyName") or "").upper()
        pre = safe_float(a.get("preRate", 0)) * 100
        dt = a.get("dateHour', None")  if False else a.get("dateHour")  # placeholder safe access
        # use dateHour if available
        time_str = ms_to_utc_time(a.get("dateHour")) if a.get("dateHour") else "N/A"
        pairs.append((name, pre, time_str))
    # remove empty names and sort
    pairs = [p for p in pairs if p[0]]
    pairs.sort(key=lambda x: x[1], reverse=True)

    tickers = [f"{name}" for name, _, _ in pairs]
    reply_markup = build_paginated_keyboard(tickers, page, prefix="pairs")
    # Build text for this page
    start = page * PAGE_SIZE
    page_chunk = pairs[start:start + PAGE_SIZE]
    lines = [f"{n} — {apr:.2f}% ({t})" for n, apr, t in page_chunk]
    text = "📋 All Pairs (sorted by current APR desc)\n\n" + ("\n".join(lines) if lines else "No pairs found.")
    await query.edit_message_text(text, reply_markup=reply_markup)

# ---- Pair selected from pairs list ----
async def pairs_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # callback format pairs_item_{TICKER}
    try:
        ticker = query.data.split("_", 2)[2].upper()
    except Exception:
        await query.edit_message_text("Invalid pair selection.")
        return
    assets = fetch_assets()
    asset = find_asset_by_ticker(ticker, assets)
    if not asset:
        await query.edit_message_text(f"Ticker {ticker} not found.")
        return
    pre = safe_float(asset.get("preRate", 0)) * 100
    est = safe_float(asset.get("estimatedRate", 0)) * 100
    last_time = ms_to_utc_dt(asset.get("dateHour")) if asset.get("dateHour") else "N/A"
    msg = (
        f"♻ {ticker} Lending Rates at {last_time}\n"
        f"💰 Current rate: {pre:.2f}%\n"
        f"📈 Predicted rate: {est:.2f}%"
    )
    kb = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
         InlineKeyboardButton("📊 History", callback_data=f"history_item_{ticker}")],
        [InlineKeyboardButton("⬅ Back to Pairs", callback_data="pairs_page_0"),
         InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))

# ---- Refresh handler ----
async def refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        ticker = query.data.split("_", 1)[1].upper()
    except Exception:
        await query.edit_message_text("Invalid refresh request.")
        return
    assets = fetch_assets(force=True)
    asset = find_asset_by_ticker(ticker, assets)
    if not asset:
        await query.edit_message_text(f"Ticker {ticker} not found.")
        return
    pre = safe_float(asset.get("preRate", 0)) * 100
    est = safe_float(asset.get("estimatedRate", 0)) * 100
    last_time = ms_to_utc_dt(asset.get("dateHour")) if asset.get("dateHour") else "N/A"
    msg = (
        f"♻ {ticker} Lending Rates at {last_time}\n"
        f"💰 Current rate: {pre:.2f}%\n"
        f"📈 Predicted rate: {est:.2f}%"
    )
    kb = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
         InlineKeyboardButton("📊 History", callback_data=f"history_item_{ticker}")],
        [InlineKeyboardButton("⬅ Back to Pairs", callback_data="pairs_page_0"),
         InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))

# ---- History menu (only supported CURRENCY_IDS, sorted by latest APR desc) ----
async def history_menu_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split("_")[-1])
    except Exception:
        page = 0
    assets = fetch_assets()
    records = []
    for ticker, cid in CURRENCY_IDS.items():
        asset = find_asset_by_ticker(ticker, assets)
        if not asset:
            continue
        pre = safe_float(asset.get("preRate", 0)) * 100
        hh = ms_to_utc_time(asset.get("dateHour")) if asset.get("dateHour") else "N/A"
        records.append((ticker, pre, hh))
    records.sort(key=lambda x: x[1], reverse=True)
    reply_markup = build_history_menu_keyboard(records, page)
    # build text page
    start = page * PAGE_SIZE
    chunk = records[start:start + PAGE_SIZE]
    lines = [f"{t} — {apr:.2f}% ({hh})" for t, apr, hh in chunk]
    text = "📊 History (supported pairs) — latest APR\n\n" + ("\n".join(lines) if lines else "No records.")
    await query.edit_message_text(text, reply_markup=reply_markup)

# ---- History item detail: last 24 hours + average APR for today (UTC) ----
async def history_item_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        ticker = query.data.split("_", 2)[2].upper()
    except Exception:
        await query.edit_message_text("Invalid history selection.")
        return
    cid = CURRENCY_IDS.get(ticker)
    if not cid:
        await query.edit_message_text(f"{ticker} is not supported for history.")
        return
    entries = fetch_history_entries(cid)
    if not entries:
        await query.edit_message_text(f"No history data for {ticker}.")
        return

    # take newest 24 entries
    last24 = entries[:24]
    now_date = datetime.now(timezone.utc).date()
    today_rates = []
    lines = []
    for e in last24:
        rate_pct = safe_float(e.get("rate", 0)) * 100
        dt = ms_to_utc_dt(e.get("dateHour")) if e.get("dateHour") else "N/A"
        lines.append(f"{dt} — {rate_pct:.2f}%")
        try:
            d_obj = datetime.fromtimestamp(e.get("dateHour") / 1000, tz=timezone.utc).date()
            if d_obj == now_date:
                today_rates.append(rate_pct)
        except Exception:
            pass

    avg_today = sum(today_rates) / len(today_rates) if today_rates else 0.0
    header = f"📊 {ticker} Lending Rate — Last {len(last24)} records\n\n📌 Average APR for {now_date.isoformat()} (UTC): {avg_today:.2f}%\n\n"
    text = header + "\n".join(lines)
    kb = [
        [InlineKeyboardButton("📋 View All Pairs", callback_data="pairs_page_0"),
         InlineKeyboardButton("⬅ Back to History", callback_data="history_page_0")],
        [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ---- Back to menu ----
async def back_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("📋 View All Pairs", callback_data="pairs_page_0")],
        [InlineKeyboardButton("🔍 Search (ticker)", callback_data="search_prompt")],
        [InlineKeyboardButton("📊 History", callback_data="history_page_0")]
    ]
    await query.edit_message_text("Main menu:", reply_markup=InlineKeyboardMarkup(kb))

# ---- Pairs search (filter) flow ----
async def pairs_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_pairs_search"] = True
    await query.edit_message_text("Enter substring to search pairs (e.g. 'ETH' or 'US'):")
    return PAIRS_FILTER_INPUT

async def pairs_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    context.user_data["awaiting_pairs_search"] = False
    assets = fetch_assets()
    tickers = sorted({(a.get("currencyName") or "").upper() for a in assets if a.get("currencyName")})
    filtered = [t for t in tickers if text in t]
    if not filtered:
        await update.message.reply_text(f"No pairs match '{text}'.")
        return ConversationHandler.END
    # store filtered list in user_data for pagination
    context.user_data["pairs_filtered"] = filtered
    # send first page of filtered results
    markup = build_paginated_keyboard(filtered, 0, prefix="pairs_filtered")
    # build text for first page
    lines = []
    for t in filtered[:PAGE_SIZE]:
        asset = find_asset_by_ticker(t, assets)
        if asset:
            apr = safe_float(asset.get("preRate", 0)) * 100
            dt = ms_to_utc_time(asset.get("dateHour")) if asset.get("dateHour") else "N/A"
            lines.append(f"{t} — {apr:.2f}% ({dt})")
    text = f"Search results for '{text}':\n\n" + ("\n".join(lines) if lines else "No matches.")
    await update.message.reply_text(text, reply_markup=markup)
    return ConversationHandler.END

# ---- Generic callback router ----
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = (query.data or "")
    logger.info("Callback data received: %s from user %s", data, update.effective_user.id if update.effective_user else None)

    # pairs pages and items
    if data.startswith("pairs_page_"):
        return await pairs_page_handler(update, context)
    if data.startswith("pairs_item_") or data.startswith("pairs_item_"):  # kept for clarity
        return await pairs_item_handler(update, context)
    if data.startswith("pairs_item_") is False and data.startswith("pairs_item_") is False:
        pass

    if data.startswith("pairs_item_"):
        return await pairs_item_handler(update, context)
    # generic "pairs" items built with prefix 'pairs_item_' in build_paginated_keyboard; but we used 'pairs_item_{TICKER}'
    if data.startswith("pairs_item_") or data.startswith("pairs_item_"):
        return await pairs_item_handler(update, context)

    # filtered pairs pagination (prefix 'pairs_page_' used for both full and filtered; for filtered we check user_data)
    if data.startswith("pairs_page_"):
        # reuse pairs_page_handler but it will display full list page; for filtered we support different prefix in build if desired
        return await pairs_page_handler(update, context)

    # handle pair selection from paginated keyboard: prefix 'pairs_item_{TICKER}'
    if data.startswith("pairs_item_"):
        return await pairs_item_handler(update, context)

    # refresh
    if data.startswith("refresh_"):
        return await refresh_handler(update, context)

    # search prompt
    if data == "search_prompt":
        return await search_prompt_cb(update, context)

    # pairs filter search start
    if data == "pairs_search":
        return await pairs_search_prompt(update, context)

    # direct pair selection callback pattern 'pair_{TICKER}' (older patterns)
    if data.startswith("pair_"):
        # convert to "pairs_item" handling; create a temporary query.data to expected value
        query.data = f"pairs_item_{data.split('_',1)[1]}"
        return await pairs_item_handler(update, context)

    # history menu pages
    if data.startswith("history_page_"):
        return await history_menu_page(update, context)
    # history item selected
    if data.startswith("history_item_"):
        return await history_item_detail(update, context)
    # history item produced originally as 'history_item_{TICKER}'
    if data.startswith("history_item_"):
        return await history_item_detail(update, context)

    # history item older pattern 'history_{TICKER}'
    if data.startswith("history_") and not data.startswith("history_item_"):
        # convert
        parts = data.split("_", 1)
        if len(parts) == 2:
            ticker = parts[1]
            query.data = f"history_item_{ticker}"
            return await history_item_detail(update, context)

    # back to menu
    if data == "back_menu":
        return await back_menu_handler(update, context)

    # fallback
    await query.answer("Unknown action", show_alert=True)
    logger.warning("Unhandled callback data: %s", data)

# -------------------------
# Setup and run
# -------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation for search ticker
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_prompt_cb, pattern="^search_prompt$")],
        states={SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_handler)]},
        fallbacks=[],
        allow_reentry=True,
    )

    # Conversation for pairs filter search
    pairs_search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pairs_search_prompt, pattern="^pairs_search$")],
        states={PAIRS_FILTER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pairs_search_input)]},
        fallbacks=[],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(search_conv)
    app.add_handler(pairs_search_conv)
    app.add_handler(CallbackQueryHandler(callback_router))
    # direct text as quick ticker lookup (if user just types ticker)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_handler))

    logger.info("Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
