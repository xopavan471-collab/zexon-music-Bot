import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from yt_dlp import YoutubeDL

TOKEN = ("8986816218:AAF9eTDjk8wHeMgvvSpUNgmdRqWl35cCCFs")

# --- START MESSAGE - Tere screenshot jaisa ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    text = (
        f"Welcome, {user_name.upper()} !!\n\n"
        "Type a song name, artist, or even lyrics — I'll find and send it.\n\n"
        "You can also send a voice message with music for recognition.\n\n"
        "/legal — Legal info & copyright\n\n"
        "Bot created with\n"
        "@zexon_x"
    )
    keyboard = [
        [
            InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇꜱ", callback_data="daily_top"),
            InlineKeyboardButton("ᴀʙᴏᴜᴛ", callback_data="top_100")
        ],
        [
            InlineKeyboardButton("ʜᴇʟᴘ", callback_data="ai_music")
        ]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def legal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("This bot is for educational purpose only. All copyrights belong to respective owners.")

# --- Link bhejne par Music/Thumbnail ka option ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("Send you tube Link ❌")
        return

    context.user_data['last_url'] = url
    keyboard = [
        [InlineKeyboardButton("𝐌𝐮𝐬𝐢𝐜 🎵", callback_data="music")],
        [InlineKeyboardButton("𝐓𝐡𝐮𝐦𝐛𝐧𝐚𝐢𝐥 🖼️", callback_data="thumb")]
    ]
    await update.message.reply_text("What do you want to Download 👇", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Saare Buttons ka kaam ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = context.user_data.get('last_url')
    choice = query.data

    # Start wale 3 buttons
    if choice == "daily_top":
        await query.edit_message_text("Click Here: https://t.me/zexon_Bot_updates)
        return
    if choice == "top_100":
        await query.edit_message_text("name: zexon music Bot")
        return
    if choice == "ai_music":
        await query.edit_message_text("Help For Contact: @zexon_x")
        return

    if not url:
        await query.edit_message_text("Please send Link !")
        return

    try:
        if choice == "thumb":
            await query.edit_message_text("Thumbnail Downloading... ⚙️")
            ydl_opts = {'skip_download': True, 'quiet': True}
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                thumb_url = info.get('thumbnail')
                title = info.get('title', 'Thumbnail')
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=thumb_url, caption=f"📸 {title}")
            await query.delete_message()

        elif choice == "music":
            await query.edit_message_text("Music downloading...⚙️)
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
                'quiet': True
            }
            os.makedirs("downloads", exist_ok=True)
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                audio_file = ydl.prepare_filename(info)
                audio_file = os.path.splitext(audio_file)[0] + ".mp3"
            with open(audio_file, 'rb') as f:
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=f, title=info.get('title'))
            os.remove(audio_file)
            await query.delete_message()

    except Exception as e:
        await query.edit_message_text(f"Failed ❌\n{e}")

def main():
    if not TOKEN:
        print("BOT_TOKEN nahi mila!")
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
