import os
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# Load .env locally
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

API_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"

# Store asset list in memory
assets_list = []

# --- Fetch all assets ---
def fetch_assets():
    global assets_list
    try:
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "data" in data and "list" in data["data"]:
            items = data["data"]["list"]
            if isinstance(items, dict):
                items = [items]
            assets_list = items
            return True
    except Exception as e:
        print(f"Error fetching assets: {e}")
    return False

# --- Get rate for a specific asset ---
def get_asset_rate(ticker):
    for item in assets_list:
        if item.get("currencyName", "").upper() == ticker.upper():
            pre = float(item.get("preRate", 0)) * 100
            est = float(item.get("estimatedRate", 0)) * 100
            return pre, est
    return None

# --- Start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if fetch_assets():
        await update.message.reply_text(
            "📊 Welcome! You can select a crypto from the list or type its ticker (e.g., TON)\n"
            "Use /list to browse available assets."
        )
    else:
        await update.message.reply_text("❌ Failed to fetch assets. Try again later.")

# --- List command with pagination ---
async def list_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    await send_asset_page(update, context, page)

async def send_asset_page(update, context, page):
    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page
    chunk = assets_list[start_idx:end_idx]

    keyboard = [
        [InlineKeyboardButton(f"{item['currencyName']}", callback_data=f"asset_{item['currencyName']}")]
        for item in chunk
    ]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))
    if end_idx < len(assets_list):
        nav_buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(f"📄 Page {page+1}", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(f"📄 Page {page+1}", reply_markup=reply_markup)

# --- Handle button clicks ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("page_"):
        page = int(query.data.split("_")[1])
        await send_asset_page(update, context, page)
    elif query.data.startswith("asset_"):
        ticker = query.data.split("_")[1]
        rates = get_asset_rate(ticker)
        if rates:
            pre, est = rates
            await query.edit_message_text(
                f"💰 *{ticker} Lending Rates*\n"
                f"Current rate: {pre:.2f}%\n"
                f"Estimated rate: {est:.2f}%",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(f"❌ No data for {ticker}")

# --- Handle manual text input ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip()
    rates = get_asset_rate(ticker)
    if rates:
        pre, est = rates
        await update.message.reply_text(
            f"💰 *{ticker.upper()} Lending Rates*\n"
            f"Current rate: {pre:.2f}%\n"
            f"Estimated rate: {est:.2f}%",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ No data found for '{ticker.upper()}'")

# --- Main ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_assets))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🤖 Bot is running...")
    app.run_polling()