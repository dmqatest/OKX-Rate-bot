import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

OKX_ALL_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"
OKX_HISTORY_URL = "https://www.okx.com/priapi/v2/financial/market-lending-history"

CURRENCY_IDS = {
    "USDT": 7, "USDC": 283, "TON": 2054, "ZRO": 2425497, "APT": 2092, "BERA": 3197,
    "BETH": 1620, "ETHFI": 1215929, "CVC": 54, "CVX": 1911, "BABY": 3274, "IP": 3261,
    "KMNO": 1743707, "PARTI": 3185, "MAGIC": 1970, "PENGU": 3230, "SOPH": 3293,
    "XTZ": 1029, "DOT": 1486, "JST": 1438
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📋 View All Pairs", callback_data="view_all_pairs")],
        [InlineKeyboardButton("📜 History", callback_data="history_menu")],
        [InlineKeyboardButton("🔍 Search by Ticker", switch_inline_query_current_chat="")]
    ]
    await update.message.reply_text("Select an option:", reply_markup=InlineKeyboardMarkup(keyboard))

def fetch_all_pairs():
    logger.info("Fetching all pairs...")
    r = requests.get(OKX_ALL_URL)
    r.raise_for_status()
    return r.json()

def fetch_history(currency_id):
    logger.info(f"Fetching history for currency ID {currency_id}")
    url = f"{OKX_HISTORY_URL}?currencyId={currency_id}&pageSize=300&pageIndex=1"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def format_rate(rate):
    return f"{rate:.2f}%"

def format_history(data):
    records = []
    apr_sum = 0
    count = 0
    for item in data.get("data", []):
        apr = item["rate"] * 100
        ts = datetime.utcfromtimestamp(item["dateHour"] / 1000).strftime("%Y-%m-%d %H:%M UTC")
        records.append(f"{ts} — {format_rate(apr)}")
        apr_sum += apr
        count += 1
    avg_apr = apr_sum / count if count > 0 else 0
    return records[:24], avg_apr

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "view_all_pairs":
        data = fetch_all_pairs()
        pairs = []
        for item in data.get("data", {}).get("list", []):
            if "currencyName" in item:
                rate = item.get("preRate", 0) * 100
                updated = datetime.utcfromtimestamp(item["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M UTC") if "timestamp" in item else "N/A"
                pairs.append(f"{item['currencyName']} — {format_rate(rate)} ({updated})")
        text = "📋 All Pairs:\n" + "\n".join(pairs[:50])
        await query.edit_message_text(text)

    elif query.data == "history_menu":
        keyboard = []
        for name, cid in CURRENCY_IDS.items():
            keyboard.append([InlineKeyboardButton(name, callback_data=f"history_{cid}")])
        await query.edit_message_text("Select asset for history:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("history_"):
        cid = int(query.data.split("_")[1])
        ticker = [k for k, v in CURRENCY_IDS.items() if v == cid][0]
        data = fetch_history(cid)
        records, avg_apr = format_history(data)
        text = f"{ticker} Lending Rate — Last 24 records\n\n📌 Average APR: {format_rate(avg_apr)}\n\n" + "\n".join(records)
        await query.edit_message_text(text)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
