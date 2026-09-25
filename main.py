from __future__ import annotations
import asyncio, json, logging, os, re, sqlite3, tempfile, time, requests, threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs
import httpx
from yt_dlp import YoutubeDL
from flask import Flask

TOKEN = "8986816218:AAHnfkyvQtaV_N_GaPa738zCqeFZuHzFkxU".strip()
MAX_AUDIO_BYTES = 49_000_000
DOWNLOAD_TIMEOUT_SECONDS = 45
USER_DB_PATH = Path(os.environ.get("USER_DB_PATH", "bot_users.sqlite3"))

SUPPORTED_HOSTS = (
    "youtube.com","youtu.be","music.youtube.com","m.youtube.com",
    "instagram.com","facebook.com","fb.watch",
    "tiktok.com","vt.tiktok.com","vm.tiktok.com","m.tiktok.com",
    "twitter.com","x.com","t.co",
    "soundcloud.com","spotify.com","jiosaavn.com"
)
LAST_URLS: dict[int, str] = {}

def parse_admin_ids() -> set[int]:
    admin_ids: set[int] = set()
    for value in os.environ.get("ADMIN_USER_IDS", "").split(","):
        value = value.strip()
        if value.lstrip("-").isdigit(): admin_ids.add(int(value))
    return admin_ids
ADMIN_USER_IDS = parse_admin_ids()
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("zexon-music-bot")

# ================= DB =================
def init_user_store() -> None:
    with sqlite3.connect(USER_DB_PATH) as c:
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT NOT NULL DEFAULT '', first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '', language_code TEXT NOT NULL DEFAULT '', first_seen_at INTEGER NOT NULL, last_activity_at INTEGER NOT NULL, download_count INTEGER NOT NULL DEFAULT 0)")
def record_user(user: dict[str, Any], download: bool = False) -> None:
    user_id = user.get("id")
    if not isinstance(user_id, int): return
    now = int(time.time())
    with sqlite3.connect(USER_DB_PATH) as c:
        c.execute("INSERT INTO users (user_id, username, first_name, last_name, language_code, first_seen_at, last_activity_at, download_count) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=CASE WHEN excluded.username<>'' THEN excluded.username ELSE users.username END, first_name=CASE WHEN excluded.first_name<>'' THEN excluded.first_name ELSE users.first_name END, last_name=CASE WHEN excluded.last_name<>'' THEN excluded.last_name ELSE users.last_name END, language_code=CASE WHEN excluded.language_code<>'' THEN excluded.language_code ELSE users.language_code END, last_activity_at=excluded.last_activity_at, download_count=users.download_count+excluded.download_count",
        (user_id, str(user.get("username") or ""), str(user.get("first_name") or ""), str(user.get("last_name") or ""), str(user.get("language_code") or ""), now, now, 1 if download else 0))
def safe_record_user(user: dict[str, Any], download: bool = False) -> None:
    try: record_user(user, download)
    except sqlite3.Error: logger.exception("DB fail")
def format_user_time(timestamp: int) -> str: return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def admin_report() -> str:
    with sqlite3.connect(USER_DB_PATH) as c:
        total_users, total_downloads = c.execute("SELECT COUNT(*), COALESCE(SUM(download_count),0) FROM users").fetchone()
        users = c.execute("SELECT user_id, username, first_name, last_name, last_activity_at, download_count FROM users ORDER BY last_activity_at DESC LIMIT 30").fetchall()
    lines=[f"total users: {total_users}", f"Full successful downloads: {total_downloads}", "", "After users:"]
    if not users: lines.append("अभी कोई user record नहीं है।")
    else:
        for uid, un, fn, ln, la, dl in users:
            name=" ".join(p for p in (fn, ln) if p) or "बिना नाम"; utext=f"@{un}" if un else "बिना username"
            lines.append(f"• {name} ({utext})\n ID: {uid} | downloads: {dl} | last: {format_user_time(la)}")
    return "\n".join(lines)[:3900]
def admin_stats() -> str:
    with sqlite3.connect(USER_DB_PATH) as c: total_users, total_downloads = c.execute("SELECT COUNT(*), COALESCE(SUM(download_count),0) FROM users").fetchone()
    return f"📊 Bot statistics\n\nUsers: {total_users}\nSuccessful downloads: {total_downloads}"
def is_admin(user_id: int) -> bool: return user_id in ADMIN_USER_IDS
class TelegramAPIError(RuntimeError): pass

def is_supported_url(value: str) -> bool:
    try: parsed=urlparse(value)
    except ValueError: return False
    hostname=(parsed.hostname or "").lower().removeprefix("www.")
    return parsed.scheme in {"http","https"} and any(hostname==h or hostname.endswith(f".{h}") for h in SUPPORTED_HOSTS)

def is_youtube_url(value: str) -> bool:
    try: hostname=(urlparse(value).hostname or "").lower().removeprefix("www.")
    except ValueError: return False
    if "music.youtube.com" in hostname: return False
    return hostname=="youtube.com" or hostname.endswith(".youtube.com") or hostname=="youtu.be" or hostname=="m.youtube.com"

def is_youtube_music_url(value: str) -> bool:
    try: hostname=(urlparse(value).hostname or "").lower()
    except ValueError: return False
    return "music.youtube.com" in hostname

def clean_filename(value: str, fallback: str = "audio") -> str:
    cleaned=re.sub(r"[^\w\s.-]","",value,flags=re.UNICODE); cleaned=re.sub(r"\s+"," ",cleaned).strip(); return cleaned[:100] or fallback

def get_youtube_id(url: str) -> str | None:
    try:
        parsed=urlparse(url)
        hostname=(parsed.hostname or "").lower().removeprefix("www.")
        if "youtu.be" in hostname: return parsed.path.lstrip("/").split("?")[0].split("&")[0][:11]
        qs=parse_qs(parsed.query)
        if "v" in qs: return qs["v"][0][:11]
        m=re.search(r"/(?:shorts|embed|watch)/([^/?&]+)", parsed.path)
        if m: return m.group(1)[:11]
    except Exception: pass
    m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return m.group(1) if m else None

# ========== FIX 1 & 2: TIKTOK + X FIX ==========
def resolve_tiktok_url(short_url: str) -> str:
    try:
        r = requests.get(short_url, allow_redirects=True, timeout=15, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        return r.url
    except: return short_url

def tiktok_api_download(url: str) -> tuple[str | None, str | None, str]:
    """Return thumbnail, music_url, title via TikWM"""
    try:
        r = requests.post("https://www.tikwm.com/api/", data={"url": url, "count":12,"cursor":0,"web":1,"hd":1}, timeout=20)
        j = r.json()
        data = j.get("data",{})
        title = data.get("title","TikTok Audio")[:80]
        cover = data.get("cover") or data.get("origin_cover") or data.get("ai_dynamic_cover")
        music = data.get("music") or data.get("music_info",{}).get("play") or data.get("play")
        return cover, music, title
    except Exception as e:
        logger.warning(f"TikWM API fail {e}")
        return None, None, "TikTok"

def extract_thumbnail(url: str) -> tuple[str | None, str]:
    # YT
    if is_youtube_url(url) or is_youtube_music_url(url):
        vid=get_youtube_id(url)
        if vid: return f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg", f"YouTube Video {vid}"

    # TIKTOK FIX
    if "tiktok.com" in url:
        try:
            real_url = url
            if "vt.tiktok.com" in url or "vm.tiktok.com" in url:
                real_url = resolve_tiktok_url(url)
            cover, _, title = tiktok_api_download(real_url)
            if cover: return cover, title
        except Exception: pass

    # X.COM PHOTO FIX
    if "x.com" in url or "twitter.com" in url:
        try:
            m=re.search(r"/status/(\d+)", url)
            if m:
                tid=m.group(1)
                r=requests.get(f"https://api.fxtwitter.com/status/{tid}", timeout=15, headers={"User-Agent":"Mozilla/5.0"}).json()
                tweet=r.get("tweet",{})
                # photo
                photos = tweet.get("media",{}).get("photos",[])
                if photos:
                    return photos[0].get("url"), tweet.get("text","X Post")[:100]
                # video thumb
                videos = tweet.get("media",{}).get("videos",[])
                if videos:
                    return videos[0].get("thumbnail_url"), tweet.get("text","X Post")[:100]
                # agar kuch nahi toh author avatar
                if tweet.get("author",{}).get("avatar_url"):
                    return tweet["author"]["avatar_url"], tweet.get("text","X Post")[:100]
        except Exception as e:
            logger.warning(f"X thumb fix fail {e}")

    # Normal yt-dlp
    options={"quiet":True,"no_warnings":True,"skip_download":True,"noplaylist":True,"socket_timeout":DOWNLOAD_TIMEOUT_SECONDS}
    with YoutubeDL(options) as ydl:
        info=ydl.extract_info(url, download=False)
    return info.get("thumbnail"), info.get("title") or "Thumbnail"

def download_audio(url: str, directory: str) -> tuple[Path, str]:
    # YOUTUBE MAIN BLOCK
    if is_youtube_url(url):
        raise ValueError("youtube_audio_disabled")

    # ========== TIKTOK SPECIAL LAYER ==========
    if "tiktok.com" in url:
        try:
            real_url = url
            if "vt.tiktok.com" in url or "vm.tiktok.com" in url:
                real_url = resolve_tiktok_url(url)
            cover, music_url, title = tiktok_api_download(real_url)
            if music_url:
                safe="".join(c for c in title if c not in '\\/*?:"<>|')[:70] or "tiktok"
                path=Path(directory)/f"{safe}.mp3"
                with requests.get(music_url, headers={"User-Agent":"Mozilla/5.0"}, stream=True, timeout=60) as dl:
                    with open(path,'wb') as f:
                        for chunk in dl.iter_content(8192): f.write(chunk)
                if path.stat().st_size>5000:
                    logger.info("TikWM SUCCESS")
                    return path, title
        except Exception as e:
            logger.warning(f"TikTok audio layer fail {e}")

    # ========== UNIVERSAL yt-dlp ==========
    ydl_opts={
        "format":"bestaudio/best",
        "outtmpl":os.path.join(directory, "%(title).80s.%(ext)s"),
        "noplaylist":True,
        "quiet":True,
        "no_warnings":True,
        "nocheckcertificate":True,
        "socket_timeout":DOWNLOAD_TIMEOUT_SECONDS,
        "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
    }
    with YoutubeDL(ydl_opts) as ydl:
        info=ydl.extract_info(url, download=True)
        title=info.get("title") or "Audio"
        mp3s=list(Path(directory).glob("*.mp3"))
        if not mp3s: mp3s=list(Path(directory).glob("*.*"))
        if mp3s:
            p=mp3s[0]
            if p.stat().st_size>MAX_AUDIO_BYTES: raise ValueError("audio_too_large")
            if p.stat().st_size<5000: raise ValueError("this link can't download")
            return p, title
    raise ValueError("this link can't download")

# ================= TELEGRAM =================
async def telegram_request(client: httpx.AsyncClient, method: str, data: dict[str, Any] | None = None, files: dict[str, Any] | None = None, timeout: float = 40) -> Any:
    response=await client.post(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data, files=files, timeout=timeout)
    payload=response.json()
    if not response.is_success or not payload.get("ok"): raise TelegramAPIError(f"{method}: {payload.get('description')}")
    return payload.get("result")
async def send_message(client: httpx.AsyncClient, chat_id: int, text: str, keyboard=None) -> Any:
    data={"chat_id":str(chat_id),"text":text}
    if keyboard: data["reply_markup"]=json.dumps({"inline_keyboard":keyboard},ensure_ascii=False)
    return await telegram_request(client,"sendMessage",data=data)
async def edit_message(client: httpx.AsyncClient, chat_id: int, message_id: int, text: str) -> None:
    try: await telegram_request(client,"editMessageText",data={"chat_id":str(chat_id),"message_id":str(message_id),"text":text})
    except TelegramAPIError: pass
async def answer_callback(client: httpx.AsyncClient, callback_id: str) -> None:
    try: await telegram_request(client,"answerCallbackQuery",data={"callback_query_id":callback_id})
    except TelegramAPIError: pass
async def send_photo(client: httpx.AsyncClient, chat_id: int, photo: str, caption: str) -> Any:
    return await telegram_request(client,"sendPhoto",data={"chat_id":str(chat_id),"photo":photo,"caption":caption[:900]})
async def send_audio(client: httpx.AsyncClient, chat_id: int, audio_path: Path, title: str) -> Any:
    with audio_path.open("rb") as f:
        return await telegram_request(client,"sendAudio",data={"chat_id":str(chat_id),"title":clean_filename(title),"caption":"ᴅᴏᴡɴʟᴏᴀᴅ ꜱᴜᴄᴄᴇꜰᴜʟ ✨"},files={"audio":(audio_path.name,f,"audio/mpeg")},timeout=75)
def start_keyboard(): return [[{"text":"𝐌ᴜꜱɪᴄ 🎵","callback_data":"music"},{"text":"𝐓ʜᴜᴍʙɴᴀɪʟ 🖼️","callback_data":"thumb"}],[{"text":"𝐇ᴇʟᴘ 🧑‍💻","callback_data":"help"}]]

async def handle_start(client: httpx.AsyncClient, chat_id: int, first_name: str) -> None:
    await send_message(client,chat_id,f"𝐇ᴇʏ {first_name} 👋\n\n𝐖ᴇʟᴄᴏᴍᴇ 𝐓ᴏ 𝐀ᴅᴠᴀɴᴄᴇ 𝐌ᴜ𝘀ɪᴄ 𝐀ɴᴅ 𝐓ʜᴜᴍʙɴᴀɪʟ 𝐃ᴏᴡɴʟᴏᴀᴅᴇʀ 𝐁ᴏᴛ.\n\nᴡᴇ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴꜱᴛᴀɢʀᴀᴍ ꜰᴀᴄᴇʙᴏᴏᴋ ʏᴏᴜ ᴛᴜʙᴇ ᴍᴜꜱɪᴄ ᴀɴᴅ ᴛʜᴜᴍʙɴᴀɪʟ ꜱᴇᴄᴜʀᴇ ꜰᴀꜱᴛ ꜱᴛᴀʙʟᴇ\n\n𝐆ɪᴠᴇ 𝐌ᴇ 𝐋ɪɴᴋ 𝐆ᴇᴛ 𝐌ᴜꜱɪᴄ 𝐈ɴꜱᴛᴀɴᴛʟʏ.",keyboard=start_keyboard())

async def handle_message(client: httpx.AsyncClient, message: dict[str, Any]) -> None:
    chat=message.get("chat",{}); chat_id=chat.get("id"); text=(message.get("text") or "").strip()
    if not isinstance(chat_id,int) or not text: return
    sender=message.get("from") or {}
    if isinstance(sender,dict): await asyncio.to_thread(safe_record_user,sender)
    sender_id=sender.get("id") if isinstance(sender,dict) else None
    command=text.split(maxsplit=1)[0].split("@",1)[0].lower()
    if command=="/myid": await send_message(client,chat_id,f"आपका Telegram user ID: {sender_id}"); return
    if command in {"/users","/stats"}:
        if not isinstance(sender_id,int) or not is_admin(sender_id): await send_message(client,chat_id,"यह command केवल admin के लिए उपलब्ध है।"); return
        report=await asyncio.to_thread(admin_report) if command=="/users" else await asyncio.to_thread(admin_stats)
        await send_message(client,chat_id,report); return
    if command=="/start": await handle_start(client,chat_id,(sender.get("first_name") if isinstance(sender,dict) else None) or "दोस्त"); return
    if command=="/legal": await send_message(client,chat_id,"I am bot public legally downloadable content For it"); return
    if not is_supported_url(text): await send_message(client,chat_id,"❌ Support nahi hai bhai!\n\n✅ Supported:\n• YouTube Thumbnail\n• YouTube Music\n• Instagram | Facebook\n• TikTok | Twitter/X\n• SoundCloud\n\nLink bhejo ✅"); return
    LAST_URLS[chat_id]=text
    await send_message(client,chat_id,"𝐒ᴇʟᴇᴄᴛ 𝐅ᴏʀᴍᴀᴛ :",keyboard=[[{"text":"𝐀ᴜᴅɪᴏ 🎵","callback_data":"music"},{"text":"𝐓ʜᴜᴍʙɴᴀɪʟ 🖼️","callback_data":"thumb"}]])

async def handle_callback(client: httpx.AsyncClient, callback: dict[str, Any]) -> None:
    callback_user=callback.get("from") or {}
    if isinstance(callback_user,dict): await asyncio.to_thread(safe_record_user,callback_user)
    callback_id=callback.get("id")
    if isinstance(callback_id,str): await answer_callback(client,callback_id)
    message=callback.get("message") or {}; chat_id=(message.get("chat") or {}).get("id"); message_id=message.get("message_id"); choice=callback.get("data")
    if not isinstance(chat_id,int) or not isinstance(message_id,int): return
    if choice=="help": await edit_message(client,chat_id,message_id,"Send Link, then Audio and Thumbnail Select\n\nSupports: Insta, FB, TikTok, X, SoundCloud, YT Music, YT Thumbnail\n\nHelp: @zexon_x"); return
    url=LAST_URLS.get(chat_id)
    if not url: await edit_message(client,chat_id,message_id,"Send supported Link 🔗"); return
    if choice=="thumb":
        await edit_message(client,chat_id,message_id,"Downloading...⏳")
        try:
            thumbnail,title=await asyncio.to_thread(extract_thumbnail,url)
            if not thumbnail: raise ValueError("thumbnail_missing")
            await send_photo(client,chat_id,thumbnail,title)
            if isinstance(callback_user,dict): await asyncio.to_thread(safe_record_user,callback_user,True)
            await edit_message(client,chat_id,message_id,"Here is Thumbnail ✅")
        except Exception:
            logger.exception("Thumb fail"); await edit_message(client,chat_id,message_id,"Thumbnail Download Failed! (X ka text-only tweet ho sakta hai)")
        return
    if choice!="music": return

    if is_youtube_url(url):
        await edit_message(client,chat_id,message_id,"🚫 YouTube ka Audio Replit pe block hai bhai!\n\n✅ Lekin Thumbnail mil jayega\n✅ YouTube Music / Insta / FB / TikTok / X ka Audio full chal raha hai")
        return

    await edit_message(client,chat_id,message_id,"Downloading...⏳")
    try:
        with tempfile.TemporaryDirectory(prefix="zexon-") as directory:
            audio_path,title=await asyncio.to_thread(download_audio,url,directory)
            await send_audio(client,chat_id,audio_path,title)
            if isinstance(callback_user,dict): await asyncio.to_thread(safe_record_user,callback_user,True)
        await edit_message(client,chat_id,message_id,"Here is your Audio ✅")
    except ValueError as error:
        msg=str(error)
        if msg=="audio_too_large": msg="❌ Audio Telegram limit (50MB) se bada hai"
        elif msg=="youtube_audio_disabled": msg="🚫 YouTube Audio block hai, Thumbnail try karo"
        elif "x.com" in url or "twitter.com" in url: msg="❌ X pe is tweet me video nahi hai bhai, isiliye audio nahi nikla. Video wala tweet bhejo."
        else: msg=f"❌ Audio Download Failed! Link private ho sakta hai"
        await edit_message(client,chat_id,message_id,msg)
    except Exception:
        logger.exception("Audio fail"); await edit_message(client,chat_id,message_id,"Audio download Failed! Private link ho sakta hai")

async def handle_update(client: httpx.AsyncClient, update: dict[str, Any]) -> None:
    if isinstance(update.get("message"),dict): await handle_message(client,update["message"])
    elif isinstance(update.get("callback_query"),dict): await handle_callback(client,update["callback_query"])

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "ZEXON V3 FINAL - ALL FIXED ✅ | TikTok vt link + X photo fixed"

def run_flask():
    try: flask_app.run(host='0.0.0.0', port=8080)
    except OSError: flask_app.run(host='0.0.0.0', port=3000)

async def delete_webhook_if_any():
    async with httpx.AsyncClient() as client:
        try:
            await telegram_request(client, "deleteWebhook", data={"drop_pending_updates": True})
            logger.info("Old webhook deleted - polling mode")
        except Exception: pass

async def poll_loop():
    await delete_webhook_if_any()
    async with httpx.AsyncClient(timeout=35) as client:
        offset = 0
        while True:
            try:
                result = await telegram_request(client, "getUpdates", data={"offset": str(offset), "timeout": "25"}, timeout=40)
                for update in result or []:
                    offset = int(update.get("update_id", offset)) + 1
                    await handle_update(client, update)
            except Exception as e:
                logger.warning(f"Poll error {e}")
                await asyncio.sleep(3)

def main() -> None:
    if not TOKEN or "BOT TOKEN" in TOKEN or len(TOKEN)<20:
        raise SystemExit("BOT_TOKEN env missing - Secrets me BOT_TOKEN daalo")
    init_user_store()
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Bot started V3 FINAL ALL FIXED")
    asyncio.run(poll_loop())

if __name__=="__main__": main()
