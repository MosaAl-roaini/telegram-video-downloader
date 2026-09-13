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


BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

DB_FILE = BASE_DIR / "users.db"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


# =========================
# Database
# =========================

def init_db():
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            visits INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


def save_user(user):
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        INSERT INTO users (
            user_id,
            first_name,
            last_name,
            username,
            first_seen,
            last_seen,
            visits
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)

        ON CONFLICT(user_id)
        DO UPDATE SET
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            username = excluded.username,
            last_seen = CURRENT_TIMESTAMP,
            visits = visits + 1
    """, (
        user.id,
        user.first_name,
        user.last_name,
        user.username,
    ))

    conn.commit()
    conn.close()


def get_users_count():
    conn = sqlite3.connect(DB_FILE)

    result = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()

    conn.close()

    return result[0]


def get_users():
    conn = sqlite3.connect(DB_FILE)

    rows = conn.execute("""
        SELECT
            user_id,
            first_name,
            last_name,
            username,
            first_seen,
            last_seen,
            visits
        FROM users
        ORDER BY last_seen DESC
    """).fetchall()

    conn.close()

    return rows


# =========================
# Start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # تسجيل المستخدم
    if update.effective_user:
        save_user(update.effective_user)

    await update.message.reply_text(
        "👋 أهلاً بك في بوت تحميل الفيديوهات.\n\n"
        "📎 أرسل رابط فيديو وسأحاول تحميله لك."
    )


# =========================
# Download
# =========================

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


# =========================
# Handle URL
# =========================

async def handle_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # تسجيل المستخدم حتى لو لم يضغط /start
    if update.effective_user:
        save_user(update.effective_user)

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
            for p in DOWNLOAD_DIR.glob(
                f"{user_id}_*"
            )
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

        video_file.unlink(
            missing_ok=True
        )

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
                file.unlink(
                    missing_ok=True
                )
            except OSError:
                pass


# =========================
# Admin Users
# =========================

# ضع Telegram ID الخاص بك هنا
ADMIN_ID = int(
    os.getenv("ADMIN_ID", "0")
)


async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # منع أي شخص غير الأدمن
    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ هذا الأمر خاص بالأدمن."
        )

        return

    users = get_users()

    total = len(users)

    if total == 0:

        await update.message.reply_text(
            "📊 لا يوجد مستخدمون حتى الآن."
        )

        return

    text = (
        f"👥 إجمالي المستخدمين: {total}\n\n"
    )

    for index, user in enumerate(users, start=1):

        user_id = user[0]
        first_name = user[1] or ""
        last_name = user[2] or ""
        username = user[3] or "بدون username"
        first_seen = user[4]
        last_seen = user[5]
        visits = user[6]

        name = f"{first_name} {last_name}".strip()

        text += (
            f"#{index}\n"
            f"👤 الاسم: {name}\n"
            f"🔹 Username: @{username if username != 'بدون username' else username}\n"
            f"🆔 ID: {user_id}\n"
            f"📅 أول زيارة: {first_seen}\n"
            f"🕐 آخر زيارة: {last_seen}\n"
            f"🔢 الزيارات: {visits}\n"
            f"━━━━━━━━━━━━━━\n"
        )

        # تيليجرام لديه حد لطول الرسالة
        if len(text) > 3500:

            await update.message.reply_text(
                text
            )

            text = ""

    if text:

        await update.message.reply_text(
            text
        )


# =========================
# Main
# =========================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN غير موجود في Railway Variables."
        )

    init_db()

    print(
        "BOT_TOKEN موجود:",
        bool(BOT_TOKEN)
    )

    print(
        "Users database:",
        DB_FILE
    )

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

    print(
        "🤖 Bot is running..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()

