import os
import asyncio
import sqlite3
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


# ==========================================
# الإعدادات
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

DATABASE_FILE = BASE_DIR / "bot.db"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Telegram User ID الخاص بالأدمن
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


# ==========================================
# قاعدة البيانات
# ==========================================

def init_database():
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()


def save_user(user):
    if user is None:
        return

    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute("""
            INSERT INTO users (
                user_id,
                username,
                first_name,
                last_name
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen = CURRENT_TIMESTAMP
        """, (
            user.id,
            user.username,
            user.first_name,
            user.last_name,
        ))

        connection.commit()


def get_users():
    with sqlite3.connect(DATABASE_FILE) as connection:
        cursor = connection.execute("""
            SELECT
                user_id,
                username,
                first_name,
                last_name,
                first_seen,
                last_seen
            FROM users
            ORDER BY first_seen DESC
        """)

        return cursor.fetchall()


# ==========================================
# أمر /start
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    save_user(user)

    print(
        f"START: user_id={user.id}, "
        f"username={user.username}"
    )

    await update.message.reply_text(
        "👋 أهلاً بك في بوت تحميل الفيديوهات.\n\n"
        "📎 أرسل رابط فيديو وسأحاول تحميله لك."
    )


# ==========================================
# أمر /users للأدمن
# ==========================================

async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    print(
        f"USERS COMMAND: user_id={user.id}, "
        f"ADMIN_ID={ADMIN_ID}"
    )

    if user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ ليس لديك صلاحية استخدام هذا الأمر."
        )
        return

    users = get_users()

    if not users:
        await update.message.reply_text(
            "👥 لا يوجد مستخدمون مسجلون حتى الآن."
        )
        return

    message = f"👥 إجمالي المستخدمين: {len(users)}\n\n"

    for index, row in enumerate(users, start=1):

        user_id = row[0]
        username = row[1]
        first_name = row[2] or ""
        last_name = row[3] or ""
        first_seen = row[4]
        last_seen = row[5]

        full_name = f"{first_name} {last_name}".strip()

        if not full_name:
            full_name = "بدون اسم"

        if username:
            username_text = f"@{username}"
        else:
            username_text = "لا يوجد"

        user_text = (
            f"{index}. 👤 {full_name}\n"
            f"   🆔 ID: {user_id}\n"
            f"   📱 Username: {username_text}\n"
            f"   🟢 أول استخدام: {first_seen}\n"
            f"   🔵 آخر استخدام: {last_seen}\n\n"
        )

        if len(message) + len(user_text) > 3500:
            await update.message.reply_text(message)
            message = user_text
        else:
            message += user_text

    if message.strip():
        await update.message.reply_text(message)


# ==========================================
# تحميل الفيديو
# ==========================================

def download_video(
    url: str,
    output_template: str,
):
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


# ==========================================
# استقبال رابط الفيديو
# ==========================================

async def handle_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    save_user(user)

    print(
        f"MESSAGE: user_id={user.id}, "
        f"username={user.username}"
    )

    url = (update.message.text or "").strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "❌ أرسل رابطًا صحيحًا يبدأ بـ "
            "http:// أو https://"
        )
        return

    status = await update.message.reply_text(
        "⏳ جاري تحميل الفيديو..."
    )

    user_id = user.id

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


# ==========================================
# تشغيل البوت
# ==========================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود في Railway Variables."
        )

    if not ADMIN_ID:
        raise RuntimeError(
            "ADMIN_ID غير موجود في Railway Variables."
        )

    init_database()

    print("==========================================")
    print("BOT_TOKEN موجود:", bool(BOT_TOKEN))
    print("ADMIN_ID:", ADMIN_ID)
    print("DATABASE:", DATABASE_FILE)
    print("==========================================")

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "users",
            users_command
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_url,
        )
    )

    print("🤖 Bot is running...")

    app.run_polling()


# ==========================================
# نقطة البداية
# ==========================================

if __name__ == "__main__":
    main()
