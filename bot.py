# bot.py
import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# -------------------------
# Load .env
# -------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

# -------------------------
# Constants / Config
# -------------------------
API_INFO_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
API_HISTORY_BASE = "https://www.okx.com/priapi/v2/financial/market-lending-history"

# Supported currencies for history (user-provided list)
CURRENCY_IDS = {
    "USDT": 7,
    "USDC": 283,
    "TON": 2054,
    "ZRO": 2425497,
    "APT": 2092,
    "BERA": 3197,
    "BETH": 1620,
    "ETHFI": 1215929,
    "CVC": 54,
    "CVX": 1911,
    "BABY": 3274,
    "IP": 3261,
    "KMNO": 1743707,
    "PARTI": 3185,
    "MAGIC": 1970,
    "PENGU": 3230,
    "SOPH": 3293,
    "XTZ": 1029,
    "DOT": 1486,
    "JST": 1438,
}

# UI states
SEARCH_STATE = 1

# Cached assets list (populated by fetch_assets)
assets_list = []

# -------------------------
# Helpers: API fetchers
# -------------------------
def fetch_assets():
    """Fetch market-lending-info (large list). Returns True if loaded."""
    global assets_list
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        resp = requests.get(API_INFO_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "data" in data and "list" in data["data"]:
            items = data["data"]["list"]
            if isinstance(items, dict):
                items = [items]
            assets_list = items
            return True
        else:
            print("fetch_assets: unexpected response structure", data)
    except Exception as e:
        print("fetch_assets error:", e)
    return False


def fetch_current_rate(ticker):
    """
    Fetch current loan info for ticker from market-lending-info.
    Returns (message_text, None) on success or (None, error_text) on failure.
    """
    try:
        ticker = ticker.upper()
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        resp = requests.get(API_INFO_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None, "⚠ Failed to fetch data from OKX."

        data = resp.json()
        if "data" not in data or "list" not in data["data"]:
            return None, "⚠ Unexpected API response structure."

        for entry in data["data"]["list"]:
            if entry.get("currencyName", "").upper() == ticker:
                # dateHour -> UTC time
                ts = entry.get("dateHour", 0) / 1000
                last_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                # preRate and estimatedRate may be strings or numbers
                pre = float(entry.get("preRate", 0)) * 100 if entry.get("preRate") is not None else 0.0
                est = float(entry.get("estimatedRate", 0)) * 100 if entry.get("estimatedRate") is not None else 0.0
                msg = (
                    f"♻ Updated *{ticker}* Lending Rates at {last_time}\n"
                    f"💰 Current rate: *{pre:.2f}%*\n"
                    f"📈 Estimated rate: *{est:.2f}%*"
                )
                return msg, None

        return None, f"❌ {ticker} not found in lending list."
    except Exception as e:
        print("fetch_current_rate error:", e)
        return None, f"⚠ Error fetching current rate: {e}"


def fetch_history_entries(ticker):
    """
    Returns list of history entries or (None) on error.
    Each entry expected to contain dateHour (ms) and rate.
    """
    ticker = ticker.upper()
    if ticker not in CURRENCY_IDS:
        return None
    cid = CURRENCY_IDS[ticker]
    url = f"{API_HISTORY_BASE}?currencyId={cid}&pageSize=300&pageIndex=1"
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "data" in data and "list" in data["data"]:
            items = data["data"]["list"]
            if isinstance(items, dict):
                items = [items]
            return items
        else:
            return None
    except Exception as e:
        print("fetch_history_entries error:", e)
        return None


def format_history_message(ticker, entries):
    """Format last 24 records and compute average APR for current UTC day."""
    if not entries:
        return f"⚠ No historical data available for {ticker}."

    # Take first 24 entries (API usually returns newest first)
    last24 = entries[:24]

    # Build lines
    lines = [f"📊 *{ticker}* Lending Rate — Last {len(last24)} records\n"]

    # Compute average for current UTC day
    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.date()
    rates_today = []
    for e in entries:
        try:
            ts = e.get("dateHour", 0) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if dt.date() == today_utc:
                rates_today.append(float(e.get("rate", 0)))
        except Exception:
            continue

    if rates_today:
        avg_today = sum(rates_today) / len(rates_today)
        lines.append(f"📌 Average APR for {today_utc.isoformat()} (UTC): *{avg_today:.2f}%* (based on {len(rates_today)} records)\n")
    else:
        lines.append(f"📌 Average APR for {today_utc.isoformat()} (UTC): *N/A* (no records for today)\n")

    # Append each of last24 with timestamp
    for e in last24:
        ts = e.get("dateHour", 0) / 1000
        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rate = float(e.get("rate", 0))
        lines.append(f"{dt_str} — {rate:.2f}%")

    return "\n".join(lines)


# -------------------------
# UI helpers
# -------------------------
def main_menu_markup():
    keyboard = [
        [KeyboardButton("🔍 Search by Ticker")],
        [KeyboardButton("📋 View All Pairs"), KeyboardButton("📊 History")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# -------------------------
# Handlers
# -------------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ensure assets cached (optional)
    fetch_assets()
    await update.message.reply_text(
        "📊 Welcome! Choose an option or type a ticker (e.g., TON) directly.",
        reply_markup=main_menu_markup(),
    )


# ---- Search flow (Conversation) ----
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏ Enter the crypto ticker (e.g., TON):")
    return SEARCH_STATE


async def search_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip().upper()
    msg, err = fetch_current_rate(ticker)
    if err:
        await update.message.reply_text(err)
    else:
        kb = [
            [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}")],
            [InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
            [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")],
        ]
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ---- View All Pairs (paginated from assets_list) ----
async def view_all_pairs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Load assets if not present
    if not assets_list:
        ok = fetch_assets()
        if not ok:
            await update.message.reply_text("⚠ Failed to fetch asset list from OKX.")
            return
    await send_asset_page(update, context, 0)


async def send_asset_page(update_or_query, context, page: int):
    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page
    chunk = assets_list[start_idx:end_idx]

    keyboard = [
        [InlineKeyboardButton(item.get("currencyName", "").upper(), callback_data=f"asset_{item.get('currencyName','').upper()}")]
        for item in chunk
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))
    if end_idx < len(assets_list):
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))
    if nav:
        keyboard.append(nav)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # If called from an update.message
    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(f"📄 Page {page+1}", reply_markup=reply_markup)
    else:
        # update_or_query is a CallbackQuery
        await update_or_query.edit_message_text(f"📄 Page {page+1}", reply_markup=reply_markup)


# ---- History main menu: show supported tickers (CURRENCY_IDS) paginated ----
async def history_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keys = sorted(CURRENCY_IDS.keys())
    await send_history_page(update, context, 0, keys)


async def send_history_page(update_or_query, context, page: int, keys=None):
    if keys is None:
        keys = sorted(CURRENCY_IDS.keys())
    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page
    chunk = keys[start_idx:end_idx]

    keyboard = [
        [InlineKeyboardButton(ticker, callback_data=f"hist_asset_{ticker}")] for ticker in chunk
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"hist_page_{page-1}"))
    if end_idx < len(keys):
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"hist_page_{page+1}"))
    if nav:
        keyboard.append(nav)

    reply_markup = InlineKeyboardMarkup(keyboard)
    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(f"📄 History — Page {page+1}", reply_markup=reply_markup)
    else:
        await update_or_query.edit_message_text(f"📄 History — Page {page+1}", reply_markup=reply_markup)


# ---- Generic text handler (user types ticker directly) ----
async def handle_ticker_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # If user clicked main menu buttons, they are handled separately by other handlers,
    # so here we assume it's a ticker.
    ticker = text.upper()
    msg, err = fetch_current_rate(ticker)
    if err:
        await update.message.reply_text(err)
        return
    kb = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}")],
        [InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
        [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")],
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ---- Callback handler for all inline buttons ----
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Pagination for asset list
    if data.startswith("page_"):
        page = int(data.split("_", 1)[1])
        await send_asset_page(query, context, page)
        return

    # Clicked asset in asset list -> show current rate (with buttons)
    if data.startswith("asset_"):
        ticker = data.split("_", 1)[1].upper()
        msg, err = fetch_current_rate(ticker)
        if err:
            await query.edit_message_text(err)
            return
        kb = [
            [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}")],
            [InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
            [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")],
        ]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # Refresh current rate for ticker
    if data.startswith("refresh_"):
        ticker = data.split("_", 1)[1].upper()
        msg, err = fetch_current_rate(ticker)
        if err:
            await query.edit_message_text(err)
            return
        kb = [
            [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}")],
            [InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")],
            [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")],
        ]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # Direct history viewing from current-rate button
    if data.startswith("history_"):
        ticker = data.split("_", 1)[1].upper()
        entries = fetch_history_entries(ticker)
        if entries is None:
            await query.edit_message_text(f"⚠ Failed to fetch history for {ticker}.")
            return
        history_msg = format_history_message(ticker, entries)
        kb = [
            [InlineKeyboardButton("⬅ Back to History list", callback_data="hist_back")],
            [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")],
        ]
        await query.edit_message_text(history_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # History pagination
    if data.startswith("hist_page_"):
        page = int(data.split("_", 1)[1])
        keys = sorted(CURRENCY_IDS.keys())
        await send_history_page(query, context, page, keys)
        return

    # History asset selected from history list
    if data.startswith("hist_asset_"):
        ticker = data.split("_", 1)[1].upper()
        entries = fetch_history_entries(ticker)
        if entries is None:
            await query.edit_message_text(f"⚠ Failed to fetch history for {ticker}.")
            return
        history_msg = format_history_message(ticker, entries)
        kb = [
            [InlineKeyboardButton("⬅ Back to History list", callback_data="hist_back")],
            [InlineKeyboardButton("⬅ Back to Menu", callback_data="back_menu")],
        ]
        await query.edit_message_text(history_msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # Go back to history list (from a history result)
    if data == "hist_back":
        # show first history page
        keys = sorted(CURRENCY_IDS.keys())
        await send_history_page(query, context, 0, keys)
        return

    # Back to main menu (send fresh main menu message)
    if data == "back_menu":
        chat_id = query.message.chat.id
        # Edit the current inline message to indicate we returned, and then send main menu
        try:
            await query.edit_message_text("Returned to main menu. Use the keyboard below.")
        except Exception:
            # editing might fail if the message was already removed — that's ok
            pass
        await context.bot.send_message(chat_id=chat_id, text="Main menu:", reply_markup=main_menu_markup())
        return

    # Unknown callback
    await query.edit_message_text("Unknown action.")


# -------------------------
# Boot
# -------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation for the Search button
    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Search by Ticker$"), search_start)],
        states={SEARCH_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ticker)]},
        fallbacks=[],
    )

    # Handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(search_conv)
    app.add_handler(MessageHandler(filters.Regex("^📋 View All Pairs$"), view_all_pairs_handler))
    app.add_handler(MessageHandler(filters.Regex("^📊 History$"), history_menu_handler))
    # Generic text: treat as ticker lookup if not a command/menu
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker_text))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
