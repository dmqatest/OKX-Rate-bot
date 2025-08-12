import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)

# Load environment variables locally
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing. Set it in environment variables.")

API_URL = "https://www.okx.com/priapi/v2/financial/market-lending-info?pageSize=2000&pageIndex=1"

assets_list = []  # cached list
SEARCH_STATE = 1

# Fetch all assets
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

# Get rates for ticker
def get_asset_rate(ticker):
    for item in assets_list:
        if item.get("currencyName", "").upper() == ticker.upper():
            pre = float(item.get("preRate", 0)) * 100
            est = float(item.get("estimatedRate", 0)) * 100
            return pre, est
    return None

# Start menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fetch_assets()
    keyboard = [
        [KeyboardButton("🔍 Search by Ticker")],
        [KeyboardButton("📋 View All Pairs")]
    ]
    await update.message.reply_text(
        "📊 Welcome! Choose an option:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Search handler
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏ Enter the crypto ticker (e.g., TON):")
    return SEARCH_STATE

async def search_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip()
    rates = get_asset_rate(ticker)
    if rates:
        pre, est = rates
        last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{ticker}")]]
        await update.message.reply_text(
            f"💰 *{ticker.upper()} Lending Rates at {last_update}*\n"
            f"Current rate: {pre:.2f}%\n"
            f"Estimated rate: {est:.2f}%",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ No data found for '{ticker.upper()}'")
    return ConversationHandler.END

# Paginated list
async def send_asset_page(update_or_query, context, page):
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

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(f"📄 Page {page+1}", reply_markup=reply_markup)
    else:
        await update_or_query.edit_message_text(f"📄 Page {page+1}", reply_markup=reply_markup)

# Callback buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("page_"):
        page = int(query.data.split("_")[1])
        await send_asset_page(query, context, page)

    elif query.data.startswith("asset_"):
        ticker = query.data.split("_")[1]
        rates = get_asset_rate(ticker)
        if rates:
            pre, est = rates
            last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{ticker}")]]
            await query.edit_message_text(
                f"💰 *{ticker} Lending Rates at {last_update}*\n"
                f"Current rate: {pre:.2f}%\n"
                f"Estimated rate: {est:.2f}%",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(f"❌ No data for {ticker}")

    elif query.data.startswith("refresh_"):
        ticker = query.data.split("_")[1]
        fetch_assets()
        rates = get_asset_rate(ticker)
        if rates:
            pre, est = rates
            last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{ticker}")]]
            await query.edit_message_text(
                f"♻ Updated *{ticker} Lending Rates at {last_update}*\n"
                f"Current rate: {pre:.2f}%\n"
                f"Estimated rate: {est:.2f}%",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(f"❌ No updated data for {ticker}")

# Handle text menu clicks
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 View All Pairs":
        await send_asset_page(update, context, 0)
    elif text == "🔍 Search by Ticker":
        return await search_start(update, context)

# Main
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Search by Ticker$"), search_start)],
        states={SEARCH_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_ticker)]},
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(search_conv)
    app.add_handler(MessageHandler(filters.Regex("^📋 View All Pairs$"), menu_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()
