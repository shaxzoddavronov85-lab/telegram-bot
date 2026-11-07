import asyncio
import logging
import os
import tempfile

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message
from yt_dlp import YoutubeDL

# Token hosting sozlamalaridan olinadi (kodga yozilmaydi)
BOT_TOKEN = os.environ["BOT_TOKEN"]
AUDD_API_TOKEN = os.environ.get("AUDD_API_TOKEN", "")
COOKIES_FILE = "cookies.txt"  # ixtiyoriy: YouTube bloklasa kerak bo'ladi

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

MAX_SIZE = 50 * 1024 * 1024  # Telegram bot limiti


def _download(query: str, folder: str):
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "max_filesize": MAX_SIZE,
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=True)
        entry = info["entries"][0]
        return ydl.prepare_filename(entry), entry.get("title", query), entry.get("uploader", "")


async def search_and_send(message: Message, query: str):
    status = await message.answer(f"🔎 Qidirilmoqda: {query}")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            loop = asyncio.get_running_loop()
            path, title, uploader = await loop.run_in_executor(None, _download, query, tmp)
            await message.answer_audio(FSInputFile(path), title=title, performer=uploader)
        except Exception as e:
            logging.exception(e)
            await message.answer("❌ Topilmadi yoki yuklab bo'lmadi. Boshqacha yozib ko'ring.")
    await status.delete()


async def recognize(file_path: str):
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("api_token", AUDD_API_TOKEN)
        with open(file_path, "rb") as f:
            data.add_field("file", f)
            async with session.post("https://api.audd.io/", data=data) as resp:
                js = await resp.json()
    return js.get("result")


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Salom! 🎶 Men musiqa topuvchi botman.\n\n"
        "• Qo'shiq yoki ijrochi nomini yozing\n"
        "• Yoki ovozli xabar / audio yuboring, qaysi qo'shiq ekanini aniqlayman"
    )


@dp.message(F.voice | F.audio | F.video | F.video_note)
async def on_media(message: Message):
    if not AUDD_API_TOKEN:
        await message.answer("Ovoz orqali aniqlash yoqilmagan. Qo'shiq nomini yozing.")
        return
    status = await message.answer("🎧 Tinglayapman...")
    media = message.voice or message.audio or message.video or message.video_note
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "input")
        await bot.download(media, destination=path)
        try:
            result = await recognize(path)
        except Exception as e:
            logging.exception(e)
            result = None
    await status.delete()
    if not result:
        await message.answer("😕 Aniqlay olmadim. Aniqroq/uzunroq parcha yuboring.")
        return
    artist, title = result.get("artist", ""), result.get("title", "")
    await message.answer(f"✅ Topildi: {artist} — {title}")
    await search_and_send(message, f"{artist} {title}")


@dp.message(F.text)
async def on_text(message: Message):
    await search_and_send(message, message.text.strip())


async def health(request):
    return web.Response(text="Bot ishlayapti")


async def main():
    # Render bepul reja port ochilishini talab qiladi; UptimeRobot shu manzilni "uyg'otadi"
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", "10000")))
    await site.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
