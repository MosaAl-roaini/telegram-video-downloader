import os
import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import yt_dlp


BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في بوت تحميل الفيديوهات.\n\n"
        "📎 أرسل رابط فيديو وسأحاول تحميله لك."
    )


def download_video(url: str, output_template: str):
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "❌ أرسل رابطًا صحيحًا يبدأ بـ http:// أو https://"
        )
        return

    status = await update.message.reply_text(
        "⏳ جاري تحميل الفيديو..."
    )

    user_id = update.effective_user.id

    output_template = str(
        DOWNLOAD_DIR / f"{user_id}_%(id)s.%(ext)s"
    )

    try:
        await asyncio.to_thread(
            download_video,
            url,
            output_template,
        )

        files = [
            p
            for p in DOWNLOAD_DIR.glob(f"{user_id}_*")
            if p.is_file()
        ]

        if not files:
            raise RuntimeError(
                "لم يتم العثور على الملف بعد التحميل."
            )

        video_file = max(
            files,
            key=lambda p: p.stat().st_mtime
        )

        await status.edit_text(
            "📤 تم التحميل، جاري إرسال الفيديو..."
        )

        with video_file.open("rb") as video:
            await update.message.reply_video(
                video=video,
                caption="✅ تم تحميل الفيديو بنجاح",
            )

        video_file.unlink(missing_ok=True)

    except Exception as exc:
        print(f"ERROR: {exc}")

        await status.edit_text(
            "❌ تعذر تحميل الفيديو.\n\n"
            "قد يكون الموقع غير مدعوم أو "
            "المحتوى غير متاح للتنزيل."
        )

        for file in DOWNLOAD_DIR.glob(
            f"{user_id}_*"
        ):
            try:
                file.unlink(missing_ok=True)
            except OSError:
                pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود في Railway Variables."
        )

    print("BOT_TOKEN موجود:", bool(BOT_TOKEN))

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_url,
        )
    )

    print("🤖 Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()