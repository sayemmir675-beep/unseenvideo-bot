"""
CineStream Telegram Bot
=======================
When you upload a video to this bot, it will:
1. Save the video details (title, year, quality, genre, type)
2. Auto-update movies.json (which your website reads from)
3. Post a notification to your Telegram channel with a link

SETUP (one time):
-----------------
1. Install Python 3.9+
2. pip install python-telegram-bot==20.7 aiofiles

3. Talk to @BotFather on Telegram:
   - /newbot → give it a name → get your BOT_TOKEN

4. Fill in the config below (BOT_TOKEN, CHANNEL_ID, ADSTERRA_LINK)

5. Run: python bot.py

HOW TO USE:
-----------
- Send a VIDEO file to your bot
- Bot asks: title, year, quality (HD/4K), genre, type (movie/series)
- Bot saves it and updates movies.json automatically
- Copy new entries from movies.json into your website's MOVIES array
"""

import json
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

# ============================================================
# CONFIG — reads from environment variables (Railway/Render)
# Set these in your hosting dashboard, NOT here in the code.
# For local testing only, you can hardcode them temporarily.
# ============================================================
BOT_TOKEN     = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHANNEL_ID    = os.getenv("CHANNEL_ID", "@YOUR_CHANNEL_USERNAME")
ADMIN_IDS     = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]
ADSTERRA_LINK = os.getenv("ADSTERRA_LINK", "https://adsterra.com/YOUR_DIRECT_LINK")
WEBSITE_URL   = os.getenv("WEBSITE_URL", "https://unseenvideo.tech")
DATA_FILE     = "movies.json"
# ============================================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
TITLE, YEAR, QUALITY, GENRE, TYPE, CONFIRM = range(6)

# ============================================================
# HELPERS
# ============================================================
def load_movies():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_movies(movies):
    with open(DATA_FILE, "w") as f:
        json.dump(movies, f, indent=2, ensure_ascii=False)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def movie_card_text(m):
    return (
        f"🎬 *{m['title']}* ({m['year']})\n"
        f"📺 {m['quality']} · {m['genre']} · {'🎥 Movie' if m['type']=='movie' else '📺 Series'}\n"
        f"🔗 [Watch on CineStream]({WEBSITE_URL})"
    )

# ============================================================
# COMMANDS
# ============================================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("👋 Welcome! Visit our website to browse movies.")
        return
    await update.message.reply_text(
        "👋 *CineStream Bot Admin*\n\n"
        "Commands:\n"
        "• Send a video file → add it to the library\n"
        "• /list → show all movies\n"
        "• /delete → remove a movie\n"
        "• /export → get the JS array for your website",
        parse_mode="Markdown"
    )

async def list_movies(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("No movies yet. Send a video file to add one!")
        return
    text = f"📚 *Library ({len(movies)} items)*\n\n"
    for i, m in enumerate(movies):
        text += f"{i+1}. *{m['title']}* ({m['year']}) — {m['quality']} {m['type']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def export_js(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("No movies to export yet.")
        return
    js_entries = []
    for m in movies:
        entry = (
            f"  {{\n"
            f"    title: \"{m['title']}\",\n"
            f"    year: {m['year']},\n"
            f"    quality: \"{m['quality']}\",\n"
            f"    genre: \"{m['genre']}\",\n"
            f"    type: \"{m['type']}\",\n"
            f"    thumb: \"{m.get('thumb','')}\",\n"
            f"    adLink: \"{ADSTERRA_LINK}\",\n"
            f"    videoLink: \"{m.get('videoLink','')}\"\n"
            f"  }}"
        )
        js_entries.append(entry)
    js = "const MOVIES = [\n" + ",\n".join(js_entries) + "\n];"
    # Split if too long for Telegram
    if len(js) < 4000:
        await update.message.reply_text(f"```javascript\n{js}\n```", parse_mode="Markdown")
    else:
        # Save to file and send
        with open("movies_export.js", "w") as f:
            f.write(js)
        await update.message.reply_document(
            document=open("movies_export.js", "rb"),
            filename="movies_export.js",
            caption="✅ Paste the MOVIES array into your index.html"
        )

async def delete_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    movies = load_movies()
    if not movies:
        await update.message.reply_text("No movies to delete.")
        return
    text = "Send the number of the movie to delete:\n\n"
    for i, m in enumerate(movies):
        text += f"{i+1}. {m['title']} ({m['year']})\n"
    ctx.user_data['awaiting_delete'] = True
    await update.message.reply_text(text)

# ============================================================
# ADD MOVIE CONVERSATION
# ============================================================
async def video_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Only admins can upload videos.")
        return ConversationHandler.END

    video = update.message.video or update.message.document
    if not video:
        return ConversationHandler.END

    # Save the Telegram file link
    file_id = video.file_id
    # Build a t.me deep link — replace with actual message link after forwarding
    msg_link = f"https://t.me/c/{str(update.message.chat_id).replace('-100','')}/{update.message.message_id}"
    ctx.user_data['video_link'] = msg_link
    ctx.user_data['file_id'] = file_id

    await update.message.reply_text(
        "🎬 Video received!\n\nStep 1/5: What is the *title* of this movie/series?",
        parse_mode="Markdown"
    )
    return TITLE

async def get_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['title'] = update.message.text.strip()
    await update.message.reply_text("📅 Step 2/5: What *year* was it released? (e.g. 2024)", parse_mode="Markdown")
    return YEAR

async def get_year(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or not (1900 <= int(text) <= 2030):
        await update.message.reply_text("⚠️ Please send a valid year (e.g. 2023)")
        return YEAR
    ctx.user_data['year'] = int(text)
    kb = ReplyKeyboardMarkup([["HD", "4K", "CAM", "1080p"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📺 Step 3/5: Select *quality*:", parse_mode="Markdown", reply_markup=kb)
    return QUALITY

async def get_quality(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['quality'] = update.message.text.strip()
    kb = ReplyKeyboardMarkup(
        [["Action", "Drama", "Comedy"], ["Thriller", "Sci-Fi", "Horror"], ["Romance", "Fantasy", "Crime"]],
        one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text("🎭 Step 4/5: Select *genre*:", parse_mode="Markdown", reply_markup=kb)
    return GENRE

async def get_genre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['genre'] = update.message.text.strip()
    kb = ReplyKeyboardMarkup([["movie", "series"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📂 Step 5/5: Is this a *movie* or *series*?", parse_mode="Markdown", reply_markup=kb)
    return TYPE

async def get_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().lower()
    if t not in ("movie", "series"):
        await update.message.reply_text("Please choose *movie* or *series*.", parse_mode="Markdown")
        return TYPE
    ctx.user_data['type'] = t

    d = ctx.user_data
    summary = (
        f"✅ *Confirm details:*\n\n"
        f"🎬 Title: *{d['title']}*\n"
        f"📅 Year: {d['year']}\n"
        f"📺 Quality: {d['quality']}\n"
        f"🎭 Genre: {d['genre']}\n"
        f"📂 Type: {d['type']}\n\n"
        f"Reply *yes* to save or *no* to cancel."
    )
    kb = ReplyKeyboardMarkup([["yes", "no"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=kb)
    return CONFIRM

async def confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    if answer != "yes":
        await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
        ctx.user_data.clear()
        return ConversationHandler.END

    d = ctx.user_data
    new_movie = {
        "title": d["title"],
        "year": d["year"],
        "quality": d["quality"],
        "genre": d["genre"],
        "type": d["type"],
        "thumb": "",
        "adLink": ADSTERRA_LINK,
        "videoLink": d.get("video_link", "")
    }

    movies = load_movies()
    movies.insert(0, new_movie)  # newest first
    save_movies(movies)

    await update.message.reply_text(
        f"✅ *{new_movie['title']}* saved!\n\n"
        f"📊 Total in library: {len(movies)}\n"
        f"Use /export to get the updated JS array for your website.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # Post to channel
    try:
        await ctx.bot.send_message(
            chat_id=CHANNEL_ID,
            text=movie_card_text(new_movie),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not post to channel: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def handle_delete_response(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get('awaiting_delete'):
        return
    text = update.message.text.strip()
    if not text.isdigit():
        return
    idx = int(text) - 1
    movies = load_movies()
    if 0 <= idx < len(movies):
        removed = movies.pop(idx)
        save_movies(movies)
        await update.message.reply_text(f"🗑️ Removed: *{removed['title']}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Invalid number.")
    ctx.user_data['awaiting_delete'] = False

# ============================================================
# MAIN
# ============================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.VIDEO | filters.Document.VIDEO, video_received)],
        states={
            TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            YEAR:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_year)],
            QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quality)],
            GENRE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_genre)],
            TYPE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_type)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_movies))
    app.add_handler(CommandHandler("export", export_js))
    app.add_handler(CommandHandler("delete", delete_movie))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_response))

    print("🤖 CineStream Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
