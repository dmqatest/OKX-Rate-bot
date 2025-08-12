import os
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load .env only in local development
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables or .env file.")

# ---- OKX API links ----
URLS = {
    "USDT": "https://www.okx.com/priapi/v2/financial/market-lending-info?currencyId=7&pageSize=20&pageIndex=1",
    "TON": "https://www.okx.com/priapi/v2/financial/market-lending-info?currencyId=2054&pageSize=20&pageIndex=1",
}

# ---- Helper function to fetch rate ----
def fetch_rate(coin: str):
    url = URLS.get(coin.upper())
    if not url:
        return None, "Coin not supported."

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "data" not in data or "list" not in data["data"]:
            return None, f"Unexpected data format: {data}"

        items = data["data"]["list"]
        if isinstance(items, dict):
            items = [items]

        for item in items:
            if item.get("currencyName", "").upper() == coin.upper():
                pre_rate = float(item.get("preRate", 0)) * 100
                estimated_rate = float(item.get("estimatedRate", 0)) * 100
                return (pre_rate, estimated_rate), None

        return None, f"{coin} not found in response."

    except Exception as e:
        return None, str(e)

# ---- Bot commands ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Use /usdt or /ton to check current lending rates."
    )

async def get_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rates, error = fetch_rate("USDT")
    if error:
        await update.message.reply_text(f"❌ Error: {error}")
    else:
        pre, est = rates
        await update.message.reply_text(
            f"💰 *USDT Lending Rates*\n"
            f"Current rate: {pre:.2f}%\n"
            f"Estimated rate: {est:.2f}%",
            parse_mode="Markdown"
        )

async def get_ton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rates, error = fetch_rate("TON")
    if error:
        await update.message.reply_text(f"❌ Error: {error}")
    else:
        pre, est = rates
        await update.message.reply_text(
            f"💎 *TON Lending Rates*\n"
            f"Current rate: {pre:.2f}%\n"
            f"Estimated rate: {est:.2f}%",
            parse_mode="Markdown"
        )

# ---- Main ----
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("usdt", get_usdt))
    app.add_handler(CommandHandler("ton", get_ton))

    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling()
