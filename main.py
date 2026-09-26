import os
import asyncio
import glob
import yt_dlp
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest
from telegram.request import HTTPXRequest

BOT_TOKEN = "8986816218:AAHnfkyvQtaV_N_GaPa738zCqeFZuHzFkxU"

def add_user(uid):
    try:
        if not os.path.exists("users.txt"): open("users.txt","w").close()
        users = open("users.txt").read().split()
        if str(uid) not in users:
            open("users.txt","a").write(f"{uid}\n")
    except: pass

class UploadProgressFile:
    def __init__(self, path):
        self.f = open(path, 'rb')
        self.size = os.path.getsize(path)
        self.uploaded = 0
        self.p = 0
    def read(self, n=-1):
        chunk = self.f.read(n if n!=-1 else 1024*1024)
        if chunk:
            self.uploaded += len(chunk)
            self.p = int(self.uploaded*100/self.size)
        return chunk

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id)
    name = update.effective_user.first_name

    keyboard = [
        [
            InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/zexon_Bot_updates" ),
            InlineKeyboardButton("ꜱᴜᴘᴘᴏʀᴛ", url="https://t.me/URL_Save_Bot")
        ],
        [
            InlineKeyboardButton("ᴀʙᴏᴜᴛ", callback_data="about_bot"),
        ],
        [
            InlineKeyboardButton("ꜱʜᴀʀᴇ", url="https://t.me/zexon_music_Bot"),
            InlineKeyboardButton("ʜᴇʟᴘ", url="https://t.me/zexon_x")
        ],
        [
            InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"𝐇ᴇʏ {name} ✨\n\n"
        f"𝐖ᴇʟᴄᴏᴍᴇ 𝐓ᴏ 𝐀ᴅᴠᴀɴᴄᴇ 𝐌ᴜꜱɪᴄ 𝐀ɴᴅ 𝐓ʜᴜᴍʙɴᴀɪʟ 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ.\n\n"
        f"ᴡᴇ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴꜱᴛᴀɢʀᴀᴍ ꜰᴀᴄᴇʙᴏᴏᴋ ʏᴏᴜ ᴛᴜʙᴇ ᴍᴜꜱɪᴄ ᴀɴᴅ ᴛʜᴜᴍʙɴᴀɪʟ ꜱᴇᴄᴜʀᴇ ꜰᴀꜱᴛ ꜱᴛᴀʙʟᴇ\n\n"
        f"𝐆ɪᴠᴇ 𝐌ᴇ 𝐋ɪɴᴋ 𝐆ᴇᴛ 𝐌ᴜꜱɪᴄ 𝐈ɴꜱᴛᴀɴᴛʟʏ."
    )
    await update.message.reply_text(text, reply_markup=reply_markup)

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id)
    url = update.message.text.strip()
    if not url.startswith("http"): return

    if "facebook.com/share/v" in url or "fb.watch" in url:
        url = url.split("?")[0]

    context.user_data['target_url'] = url

    keyboard = [
        [
            InlineKeyboardButton("𝐀ᴜᴅɪᴏ 🎵", callback_data="dl_audio"),
            InlineKeyboardButton("𝐓ʜᴜᴍʙɴᴀɪʟ 🖼", callback_data="dl_thumb")
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="close")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("**𝐒ᴇʟᴇᴄᴛ 𝐅ᴏʀᴍᴀᴛ:**", reply_markup=reply_markup, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "close":
        try: await query.message.delete()
        except: pass
        return

    if data == "about_bot":
        await query.answer("Zexon Music & Thumbnail Bot", show_alert=True)
        return

    url = context.user_data.get('target_url')
    if not url:
        try: await query.edit_message_text("❌ Session expired! Please send the link again.")
        except BadRequest: pass
        return

    is_thumbnail_only = (data == "dl_thumb")
    is_audio_only = (data == "dl_audio")

    for f in glob.glob("downloads/*"):
        try: os.remove(f)
        except: pass
    os.makedirs("downloads", exist_ok=True)

    try:
        await query.edit_message_text("Prosessing...⚡")
    except BadRequest:
        pass

    prog_data = {"p": 0}
    def hook(d):
        if d['status'] == 'downloading':
            try:
                tot = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
                cur = d.get('downloaded_bytes', 0)
                prog_data["p"] = int(cur * 100 / tot)
            except: pass

    try:
        await query.edit_message_text("Downloading...⏳ ")
    except BadRequest:
        pass

    async def down_updater():
        last_p = -1
        while True:
            try:
                current_p = prog_data['p']
                if current_p != last_p:
                    await query.edit_message_text(f"Downloading...⏳ {current_p} %")
                    last_p = current_p
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    pass
            except:
                pass
            await asyncio.sleep(0.8)

    task = asyncio.create_task(down_updater())
    file_path = None
    thumb_path = None

    try:
        # YouTube aur any platforms ke liye updated anti-block options
        opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'writethumbnail': True,
            'skip_download': is_thumbnail_only,
            'progress_hooks': [hook],
            'quiet': True, 
            'noplaylist': True,
            'nocheckcertificate': True,
            'cookiefile':'cookies.txt',
            'geo_bypass': True,
            'extractor_args': {
                'facebook': {'legacy': []},
                'youtube': {'player_client': ['ios', 'web', 'android']}
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }

        if is_audio_only:
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            opts['format'] = 'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bestaudio/best'
            opts['merge_output_format'] = 'mp4'

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=not is_thumbnail_only)

            if not is_thumbnail_only:
                file_path = ydl.prepare_filename(info)
                if is_audio_only:
                    base_name, _ = os.path.splitext(file_path)
                    file_path = base_name + '.mp3'

            # 1st Method: Check local downloaded thumbnail files
            base = os.path.splitext(file_path)[0] if file_path else "downloads/temp"
            for ext in ['.webp','.jpg','.jpeg','.png']:
                potential_thumb = base + ext
                if os.path.exists(potential_thumb):
                    thumb_path = potential_thumb
                    break

            if not thumb_path:
                thumbs = glob.glob("downloads/*.webp") + glob.glob("downloads/*.jpg") + glob.glob("downloads/*.png")
                if thumbs: thumb_path = sorted(thumbs, key=os.path.getctime, reverse=True)[0]

            # 2nd Method (Fallback): If yt-dlp didn't save thumbnail file, download it from info URL
            if not thumb_path and info:
                thumb_url = info.get('thumbnail')
                if thumb_url:
                    try:
                        r = requests.get(thumb_url, timeout=10)
                        if r.status_code == 200:
                            thumb_path = "downloads/fallback_thumb.jpg"
                            with open(thumb_path, 'wb') as tf:
                                tf.write(r.content)
                    except:
                        pass

            if not is_thumbnail_only and (not file_path or not os.path.exists(file_path)):
                all_files = [f for f in glob.glob("downloads/*") if not f.endswith(('.webp','.jpg','.png'))]
                if all_files: file_path = sorted(all_files, key=os.path.getctime, reverse=True)[0]

        task.cancel()
    except Exception as e:
        task.cancel()
        try: await query.edit_message_text(f"Failed ❌ : {e}")
        except BadRequest: pass
        return

    # Agar user ne Thumbnail manga ho
    if is_thumbnail_only:
        try: await query.message.delete()
        except: pass
        if thumb_path and os.path.exists(thumb_path):
            with open(thumb_path, 'rb') as t_file:
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=t_file, caption="Success Thumbnail 🖼️", parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Thumbnail not found for this link.")
        return

    if not file_path or not os.path.exists(file_path):
        try: await query.edit_message_text("Failed ❌")
        except BadRequest: pass
        return

    prog = UploadProgressFile(file_path)
    try:
        thumb_file = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
        try: await query.edit_message_text(f"Downloading...⏳ ")
        except BadRequest: pass

        if is_audio_only:
            await context.bot.send_audio(chat_id=query.message.chat_id, audio=prog, thumbnail=thumb_file, title="ZEXON MUSIC", performer="ZEXON BOT")
        else:
            await context.bot.send_video(chat_id=query.message.chat_id, video=prog, thumbnail=thumb_file, supports_streaming=True)

        try: await query.message.delete()
        except: pass

        if thumb_file: thumb_file.close()
    except Exception as e:
        try: await query.edit_message_text(f"Failed ❌ : {e}")
        except BadRequest: pass
    finally:
        try: prog.f.close()
        except: pass
        for f in glob.glob("downloads/*"):
            try: os.remove(f)
            except: pass

# Custom request settings with increased timeouts for hosting panels
request = HTTPXRequest(
    connection_pool_size=8,
    read_timeout=30.0,
    write_timeout=30.0,
    connect_timeout=30.0,
    pool_timeout=30.0
)

app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.add_handler(CallbackQueryHandler(button_callback))
print("ZEXON BOT - Audio/Thumbnail & Auto Delete Progress ON")
app.run_polling()
        
