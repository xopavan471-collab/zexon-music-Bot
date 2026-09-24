import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from yt_dlp import YoutubeDL

TOKEN = "8986816218:AAF9eTDjk8wHeMgvvSpUNgmdRqWl35cCCFs"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f" **Hi, {update.effective_user.first_name.upper()}**✨\n\n"
        f" ****Welcome to You tube Instagram Facebook Music thumbnail Download Bot\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f" How to use Read this\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Send the YouTube Instagram Facebook Link send me Here\n"
        f"then Music And Thumbnail select Anyone then Get your instantly music and thumbnail\n"
        f"Please Share And Give Support.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"

    )
    keyboard = [
        [InlineKeyboardButton(" Music 🎵", callback_data="daily_top"),
         InlineKeyboardButton("thumbnail 🎬", callback_data="top_100")],
        [InlineKeyboardButton("About ✨", callback_data="ai_music")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def legal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("For educational purpose only.\nJoin: https://t.me/zexon_Bot_updates")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "http" not in url:
        await update.message.reply_text("Send only you tube Instagram Facebook Link ✅")
        return
    context.user_data['last_url'] = url
    keyboard = [
        [InlineKeyboardButton("Music 🎵", callback_data="music")],
        [InlineKeyboardButton("Thumbnail 🖼️", callback_data="thumb")]
    ]
    await update.message.reply_text("What Do You want to Download 👇", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = context.user_data.get('last_url')
    choice = query.data

    if choice in ["daily_top", "top_100", "ai_music"]:
        await query.edit_message_text("this Feature is Not Available And Join this Channel.\n\nJoin: https://t.me/zexon_Bot_updates")
        return

    try:
        if choice == "thumb":
            await query.edit_message_text("Downloading...⏳")
            with YoutubeDL({'skip_download': True, 'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=info.get('thumbnail'), caption=info.get('title'))
            await query.edit_message_text("Here is the ✅")

        elif choice == "music":
            await query.edit_message_text("Music download ho raha hai... 🎵")
            os.makedirs("downloads", exist_ok=True)
            opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
                'quiet': True
            }
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                audio_file = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".mp3"

            with open(audio_file, 'rb') as f:
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=f, title=info.get('title'))
            os.remove(audio_file)
            await query.edit_message_text("Here is the ✅")

    except Exception as e:
        await query.edit_message_text(f"Fail ho gaya ❌ {e}")

def main():
    if not TOKEN:
        print("BOT_TOKEN nahi mila! export BOT_TOKEN karke chalao")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("legal", legal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_click))
    print("Bot Started!")
    app.run_polling()

if __name__ == "__main__":
    main()
