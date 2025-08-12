import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==========================
# LOAD ENV VARIABLES
# ==========================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

# ==========================
# SUPPORTED CURRENCIES
# ==========================
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

# ==========================
# API Helpers
# ==========================
def fetch_current_rate(ticker):
    ticker = ticker.upper()
    url = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)

    if resp.status_code != 200:
        return None, "⚠ Failed to fetch data."

    data = resp.json()
    if "data" not in data or "list" not in data["data"]:
        return None, "⚠ Unexpected API response."

    for entry in data["data"]["list"]:
        if entry.get("currencyName", "").upper() == ticker:
            ts = entry["dateHour"] / 1000
            last_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            return (
                f"♻ Updated *{ticker}* Lending Rates at {last_time}\n"
                f"💰 Current rate: *{entry['preRate']:.2f}%*\n"
                f"📈 Estimated rate: *{entry['estimatedRate']:.2f}%*",
                None
            )

    return None, f"❌ {ticker} not found in lending list."

def fetch_history(ticker):
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

    history = data["data"]["list"]
    output = [f"📊 *{ticker}* Lending Rate - Last 24h\n"]

    for entry in history[:24]:
        ts = entry["dateHour"] / 1000
        time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        output.append(f"{time_str} — {entry['rate']:.2f}%")

    return "\n".join(output)

# ==========================
# Telegram Handlers
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Send me a ticker (e.g., USDT) to get its lending rate.\n"
        "You can also type /list to see all supported tickers."
    )

async def list_tickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tickers = sorted(CURRENCY_IDS.keys())
    msg = "📋 *Supported tickers for history:*\n" + ", ".join(tickers)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip().upper()
    msg, err = fetch_current_rate(ticker)
    if err:
        await update.message.reply_text(err)
        return

    keyboard = [
        [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}")],
        [InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")]
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("refresh_"):
        ticker = query.data.split("_")[1]
        msg, err = fetch_current_rate(ticker)
        if err:
            await query.edit_message_text(err)
        else:
            keyboard = [
                [InlineKeyboardButton("♻ Refresh", callback_data=f"refresh_{ticker}")],
                [InlineKeyboardButton("📊 History", callback_data=f"history_{ticker}")]
            ]
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("history_"):
        ticker = query.data.split("_")[1]
        history_text = fetch_history(ticker)
        await query.edit_message_text(history_text, parse_mode="Markdown")

# ==========================
# Main
# ==========================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_tickers))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
