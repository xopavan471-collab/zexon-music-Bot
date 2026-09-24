import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# Yahan apna Telegram Bot Token dalein
TOKEN = "8986816218:AAF42YtS6GZl_uu6LDIGg65isdpMJfyItdY"

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"<b>𝐇ᴇʟʟᴏ {user_name} </b>✨\n\n"
        " 𝐈 ᴀᴍ <b>ᴀʟʟ ɪɴ ᴏɴᴇ ᴍᴜꜱɪᴄ ᴛʜᴜᴍʙɴᴀɪʟ ᴅᴏᴡɴʟᴏᴀᴅᴇʀ</b> ʙᴏᴛ✨\n\n"
        " Mujhe kisi bhi <b>ʏᴏᴜ ᴛᴜʙᴇ ɪɴꜱᴛᴀɢʀᴀᴍ ꜰᴀᴄᴇʙᴏᴏᴋ ᴛᴡɪᴛᴛᴇʀ</b> ꜱᴏꜰᴛᴏɴɪᴄ\n"
        "• ʏᴏᴜ ᴛᴜʙᴇ ꜰᴏʀ <b>ᴛʜᴜᴍʙɴᴀɪʟ + ᴍᴘ ᴀᴜᴅɪᴏ</b> milega.\n"
        "• ᴀʟʟ ᴘʟᴀᴛꜰᴏʀᴍꜱ ꜰᴏʀ ᴍᴘ ᴀᴜᴅɪᴏ ᴅᴏᴡɴʟᴏᴀᴅ</b> ꜰᴀꜱᴛ."
    )
    
    keyboard = [[InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/zexon_Bot_updates")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

# Progress Hook Function
def progress_hook(d):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%').strip()
        # Yahan aap progress dekh sakte hain agar terminal par print karna ho

# Link Handler (Download Audio & Thumbnail)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Check karein ki ye koi link hai ya nahi
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(" Link not Found ❌")
        return

    msg = await update.message.reply_text("𝐏ʀᴏɢʀᴇꜱꜱ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...🔗\n■■■□□□□□□□ 30%")

    audio_file = None
    thumbnail_file = None

    try:
        # 1. YouTube ke liye Thumbnail aur Audio dono download karne ki setting
        if "youtube.com" in url or "youtu.be" in url:
            ydl_opts_thumb = {
                'skip_download': True,
                'writethumbnail': True,
                'outtmpl': 'downloads/%(id)s',
            }
            with yt_dlp.YoutubeDL(ydl_opts_thumb) as ydl:
                info = ydl.extract_info(url, download=False)
                thumbnail_url = info.get('thumbnail')
                if thumbnail_url:
                    thumbnail_file = thumbnail_url

        await msg.edit_text("𝐀ᴜᴅɪᴏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...⚙️\n■■■■■■□□□□ 60%")

        # 2. Sabhi platforms ke liye Audio (MP3) extraction options
        ydl_opts_audio = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hook': progress_hook,
        }

        os.makedirs("downloads", exist_ok=True)

        # Download Audio
        with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_file = ydl.prepare_filename(info)
            audio_file = os.path.splitext(audio_file)[0] + ".mp3"

        await msg.edit_text("ᴀᴜᴅɪᴏ ᴜᴘʟᴏᴀᴅɪɴɢ...⚡\n■■■■■■■■■■ 100%")

        # 3. Telegram par bhejna
        # Agar thumbnail hai (YouTube ka case), toh pehle thumbnail bhejein
        if thumbnail_file and ("youtube.com" in url or "youtu.be" in url):
            await update.message.reply_photo(
                photo=thumbnail_file, 
                caption="🖼 <b>ʏᴏᴜ ᴛᴜʙᴇ ᴠɪᴅᴇᴏ ᴛʜᴜᴍʙɴᴀɪʟ</b>", 
                parse_mode="HTML"
            )

        # Audio file bhejein
        if audio_file and os.path.exists(audio_file):
            with open(audio_file, 'rb') as audio:
                await update.message.reply_audio(
                    audio=audio, 
                    caption="✨ Downloaded by Your Bot",
                    performer="Music Downloader Bot"
                )
            os.remove(audio_file) # Server clean rakhne ke liye file delete karein

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Kuch gadbadi ho gayi:\n<code>{str(e)}</code>", parse_mode="HTML")
        # Cleanup agar koi file bachi ho
        if audio_file and os.path.exists(audio_file):
            os.remove(audio_file)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot start ho gaya hai...")
    app.run_polling()

if __name__ == "__main__":
    main()
              
