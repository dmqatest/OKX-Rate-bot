import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Load .env file
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

# Supported tickers for history
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
    "JST": 1438
}

# Fetch current rate for a token
def fetch_rate(ticker: str) -> str:
    url = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        return f"⚠ Failed to fetch data for {ticker}"

    data = resp.json()
    if "data" not in data or "list" not in data["data"]:
        return "⚠ Unexpected API response."

    ticker = ticker.upper()
    for asset in data["data"]["list"]:
        if asset["currencyName"].upper() == ticker:
            pre_rate = asset["preRate"] * 100
            est_rate = asset["estimatedRate"] * 100
            updated_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            return (f"♻ Updated *{ticker}* Lending Rates at {updated_time}\n"
                    f"💰 Current rate: {pre_rate:.2f}%\n"
                    f"📈 Predicted rate: {est_rate:.2f}%")
    return f"❌ {ticker} not found."

# Fetch last 24h history
def fetch_history(ticker: str) -> str:
    ticker = ticker.upper()
    if ticker not in CURRENCY_IDS:
        return f"❌ {ticker} is not supported for history."

    url = f"https://www.okx.com/priapi/v2/financial/market-lending-history?currencyId={CURRENCY_IDS[ticker]}&pageSize=300&pageIndex=1"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code != 200:
        return f"⚠ Failed to fetch history for {ticker}."

    data = resp.json()
    if "data" not in data or "list" not in data["data"]:
        return "⚠ No history data available."

    history = data["data"]["list"][:24]
    if not history:
        return f"⚠ No records found for {ticker}."

    rates = [entry["rate"] * 100 for entry in history]
    avg_rate = sum(rates) / len(rates)

    output = [f"📊 *{ticker}* Lending Rate — Last 24 records\n"
              f"📌 Average APR for {datetime.fromtimestamp(history[0]['dateHour']/1000, tz=timezone.utc).strftime('%Y-%m-%d')} (UTC): {avg_rate:.2f}% (based on {len(rates)} records)\n"]

    for entry in history:
        ts = entry["dateHour"] / 1000
        time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        output.append(f"{time_str} — {entry['rate'] * 100:.2f}%")

    return "\n".join(output)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Search Token", callback_data="search_prompt")],
        [InlineKeyboardButton("📜 View All Pairs", callback_data="list_0")],
        [InlineKeyboardButton("📊 History", callback_data="history_menu")]
    ]
    await update.message.reply_text("Welcome! Choose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

# Search handler
async def search_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().upper()
    result = fetch_rate(query)
    keyboard = [[InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{query}"),
                 InlineKeyboardButton("📊 History", callback_data=f"history_{query}")]]
    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# Pagination for list
async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    url = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    data = resp.json()
    tickers = [asset["currencyName"].upper() for asset in data["data"]["list"]]
    tickers.sort()

    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_tickers = tickers[start_idx:end_idx]

    buttons = [[InlineKeyboardButton(t, callback_data=f"asset_{t}")] for t in page_tickers]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"list_{page-1}"))
    if end_idx < len(tickers):
        nav_buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"list_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    await update.callback_query.edit_message_text("📜 All Pairs:", reply_markup=InlineKeyboardMarkup(buttons))

# Callback handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("list_"):
        page = int(data.split("_")[1])
        await list_tokens(update, context, page)

    elif data.startswith("asset_"):
        ticker = data.split("_", 1)[1]
        result = fetch_rate(ticker)
        keyboard = [[InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
                     InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")]]
        await query.edit_message_text(result, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("refresh_"):
        ticker = data.split("_", 1)[1]
        result = fetch_rate(ticker)
        keyboard = [[InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}"),
                     InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")]]
        await query.edit_message_text(result, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "history_menu":
        buttons = [[InlineKeyboardButton(t, callback_data=f"history_{t}")] for t in CURRENCY_IDS.keys()]
        await query.edit_message_text("📊 Select a token for history:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("history_"):
        ticker = data.split("_", 1)[1]
        result = fetch_history(ticker)
        await query.edit_message_text(result, parse_mode="Markdown")

# Main
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_token))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
