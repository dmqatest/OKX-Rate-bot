import time
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "8170035745:AAFKaLysD-0e0JCE7p1E2pYzpTUV6CFZQDU"
BASE_API_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info"

def fetch_rate(symbol=None, currency_id=None):
    """Fetch current and estimated lending rate from OKX."""
    try:
        timestamp = int(time.time() * 1000)
        params = {
            "pageSize": 50,
            "pageIndex": 1,
            "t": timestamp
        }
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

        # Direct currencyId for faster query (TON)
        if currency_id:
            params["currencyId"] = currency_id
            params["pageSize"] = 20

        response = requests.get(BASE_API_URL, params=params, headers=headers)
        data = response.json()

        if "data" not in data or "list" not in data["data"]:
            return f"⚠️ Unexpected response: {data}"

        currency_list = data["data"]["list"]

        if symbol:
            coin_info = next((item for item in currency_list if item.get("currencyName") == symbol), None)
        else:
            coin_info = currency_list[0] if currency_list else None

        if not coin_info:
            return f"⚠️ {symbol if symbol else 'Coin'} not found."

        pre_rate = float(coin_info.get("preRate", 0)) * 100
        est_rate = float(coin_info.get("estimatedRate", 0)) * 100

        return (
            f"📊 *{coin_info['currencyName']} Lending Rate (OKX)*\n\n"
            f"💰 *Current Rate:* {pre_rate:.2f}%\n"
            f"🔮 *Estimated Rate:* {est_rate:.2f}%"
        )

    except Exception as e:
        return f"⚠️ Error fetching rate: {e}"

# === Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Commands:\n"
        "/usdt — USDT lending rate\n"
        "/ton — TON lending rate"
    )

async def usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = fetch_rate(symbol="USDT")
    await update.message.reply_text(message, parse_mode="Markdown")

async def ton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = fetch_rate(symbol="TON", currency_id=2054)
    await update.message.reply_text(message, parse_mode="Markdown")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("usdt", usdt))
    app.add_handler(CommandHandler("ton", ton))

    print("🤖 Bot is running. Use /start, /usdt, /ton in Telegram.")
    app.run_polling()
