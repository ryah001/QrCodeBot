#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
QRcodeBot - Bot Telegram pour générer et décoder des QR codes.
Avec génération depuis texte et images (3 modes image).
"""

import logging
import os
from io import BytesIO
import threading
import base64

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import qrcode
from PIL import Image
import numpy as np
import cv2
from flask import Flask

# --- Chargement du token ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Token Telegram introuvable (.env)")

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask ping ---
app_flask = Flask("ping")

@app_flask.route("/")
def home():
    return "QRcodeBot actif"

def run_flask():
    app_flask.run(host="0.0.0.0", port=10000)

threading.Thread(target=run_flask, daemon=True).start()

# --- MENUS ---
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🌀 Générer un QR code", callback_data="mode_generate")],
        [InlineKeyboardButton("🔍 Décoder un QR code", callback_data="mode_decode")],
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Texte → QR", callback_data="gen_text")],
        [InlineKeyboardButton("🖼️ Image → QR (données)", callback_data="gen_img_base64")],
        [InlineKeyboardButton("🎨 Image → QR stylisé", callback_data="gen_img_styled")],
        [InlineKeyboardButton("🔗 Image → QR lien", callback_data="gen_img_link")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def in_mode_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ Retour au menu", callback_data="back_to_menu")],
        [InlineKeyboardButton("🛑 Arrêter (/stop)", callback_data="stop")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- COMMANDES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Bienvenue sur *QRcodeBot*\n\nChoisis une action :",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🛑 Mode arrêté.",
        reply_markup=main_menu_keyboard()
    )

# --- CALLBACKS ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "mode_generate":
        await query.message.reply_text(
            "Choisis le type de génération :",
            reply_markup=generate_menu_keyboard()
        )

    elif data == "gen_text":
        context.user_data["mode"] = "generate"
        await query.message.reply_text(
            "📝 Envoie le texte ou lien à convertir en QR.",
            reply_markup=in_mode_keyboard()
        )

    elif data == "gen_img_base64":
        context.user_data["mode"] = "img_to_qr_base64"
        await query.message.reply_text(
            "🖼️ Envoie une image.\nElle sera encodée dans le QR.",
            reply_markup=in_mode_keyboard()
        )

    elif data == "gen_img_styled":
        context.user_data["mode"] = "img_to_qr_styled"
        await query.message.reply_text(
            "🎨 Envoie une image.\nElle sera intégrée au centre du QR.",
            reply_markup=in_mode_keyboard()
        )

    elif data == "gen_img_link":
        context.user_data["mode"] = "img_to_qr_link"
        await query.message.reply_text(
            "🔗 Envoie une image.\nUn QR avec lien sera généré.",
            reply_markup=in_mode_keyboard()
        )

    elif data == "mode_decode":
        context.user_data["mode"] = "decode"
        await query.message.reply_text(
            "🔍 Envoie une image contenant un QR code.",
            reply_markup=in_mode_keyboard()
        )

    elif data == "back_to_menu":
        context.user_data.clear()
        await query.message.reply_text(
            "Menu principal :",
            reply_markup=main_menu_keyboard()
        )

    elif data == "stop":
        context.user_data.clear()
        await query.message.reply_text(
            "🛑 Mode arrêté.",
            reply_markup=main_menu_keyboard()
        )

# --- QR TEXTE ---
def generate_qr_image_bytes(text: str) -> BytesIO:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

# --- QR IMAGE MODES ---
def image_to_qr_base64(image_bytes: bytes) -> BytesIO:
    encoded = base64.b64encode(image_bytes).decode()[:2000]
    return generate_qr_image_bytes(encoded)

def image_to_qr_styled(image_bytes: bytes) -> BytesIO:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )
    qr.add_data("QR Stylisé")
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    logo = Image.open(BytesIO(image_bytes)).convert("RGB")
    logo = logo.resize((qr_img.size[0] // 4, qr_img.size[1] // 4))

    pos = (
        (qr_img.size[0] - logo.size[0]) // 2,
        (qr_img.size[1] - logo.size[1]) // 2
    )
    qr_img.paste(logo, pos)

    bio = BytesIO()
    qr_img.save(bio, format="PNG")
    bio.seek(0)
    return bio

def image_to_qr_link() -> BytesIO:
    return generate_qr_image_bytes("https://example.com/image")

# --- DECODAGE ---
def decode_qr_from_image_bytes(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return [data] if data else []

# --- HANDLER TEXTE ---
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") == "generate":
        qr = generate_qr_image_bytes(update.message.text)
        qr.name = "qrcode.png"
        await update.message.reply_photo(photo=qr, caption="✅ QR généré.")
    else:
        await update.message.reply_text(
            "Choisis une option dans le menu.",
            reply_markup=main_menu_keyboard()
        )

# --- HANDLER IMAGE ---
async def photo_or_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    file_id = None

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type.startswith("image/"):
        file_id = update.message.document.file_id

    if not file_id:
        return

    file = await context.bot.get_file(file_id)
    bio = BytesIO()
    await file.download_to_memory(out=bio)
    image_bytes = bio.getvalue()

    if mode == "img_to_qr_base64":
        qr = image_to_qr_base64(image_bytes)

    elif mode == "img_to_qr_styled":
        qr = image_to_qr_styled(image_bytes)

    elif mode == "img_to_qr_link":
        qr = image_to_qr_link()

    elif mode == "decode":
        decoded = decode_qr_from_image_bytes(image_bytes)
        await update.message.reply_text(
            decoded[0] if decoded else "❌ Aucun QR détecté."
        )
        return

    else:
        await update.message.reply_text(
            "Choisis d'abord un mode.",
            reply_markup=main_menu_keyboard()
        )
        return

    qr.name = "qrcode.png"
    await update.message.reply_photo(photo=qr, caption="✅ QR généré.")

# --- UNKNOWN ---
async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commande inconnue. /start",
        reply_markup=main_menu_keyboard()
    )

# --- MAIN ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_or_document_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE, photo_or_document_handler))
    app.add_handler(MessageHandler(filters.ALL, unknown_handler))

    logger.info("QRcodeBot démarré")
    app.run_polling()

if __name__ == "__main__":
    main()
