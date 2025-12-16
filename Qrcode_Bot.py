#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
QRcodeBot - Bot Telegram pour générer et décoder des QR codes
avec personnalisation du style (couleur + coins arrondis).
"""

import logging
import os
from io import BytesIO
import threading
import base64

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask

# ================= ENV =================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN introuvable")

# ================= LOG =================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= FLASK PING =================
app_flask = Flask("ping")

@app_flask.route("/")
def home():
    return "QRcodeBot actif"

def run_flask():
    app_flask.run(host="0.0.0.0", port=10000)

threading.Thread(target=run_flask, daemon=True).start()

# ================= STYLE =================
COLOR_MAP = {
    "color_red": (220, 20, 60),
    "color_blue": (30, 144, 255),
    "color_green": (34, 139, 34),
    "color_purple": (138, 43, 226),
    "color_black": (0, 0, 0),
    "color_orange": (255, 140, 0),
}

# ================= MENUS =================
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌀 Générer un QR code", callback_data="mode_generate")],
        [InlineKeyboardButton("🔍 Décoder un QR code", callback_data="mode_decode")],
    ])

def generate_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Texte → QR", callback_data="gen_text")],
        [InlineKeyboardButton("🖼️ Image → QR (données)", callback_data="gen_img_base64")],
        [InlineKeyboardButton("🎨 Image → QR stylisé", callback_data="gen_img_styled")],
        [InlineKeyboardButton("🔗 Image → QR lien", callback_data="gen_img_link")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_to_menu")],
    ])

def color_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔴", callback_data="color_red"),
            InlineKeyboardButton("🔵", callback_data="color_blue"),
            InlineKeyboardButton("🟢", callback_data="color_green"),
        ],
        [
            InlineKeyboardButton("🟣", callback_data="color_purple"),
            InlineKeyboardButton("⚫", callback_data="color_black"),
            InlineKeyboardButton("🟠", callback_data="color_orange"),
        ],
    ])

def rounded_option_keyboard(enabled: bool):
    label = "✅ Coins arrondis" if enabled else "⬜ Coins arrondis"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data="toggle_rounded")],
        [InlineKeyboardButton("➡️ Continuer", callback_data="style_done")],
    ])

def in_mode_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Retour au menu", callback_data="back_to_menu")],
        [InlineKeyboardButton("🛑 Arrêter", callback_data="stop")],
    ])

# ================= COMMANDES =================
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

# ================= CALLBACKS =================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "mode_generate":
        await query.message.reply_text(
            "Choisis le type de génération :",
            reply_markup=generate_menu_keyboard()
        )

    elif data in ("gen_text", "gen_img_base64", "gen_img_styled", "gen_img_link"):
        context.user_data["mode"] = data
        context.user_data["qr_color"] = (0, 0, 0)
        context.user_data["qr_rounded"] = False
        await query.message.reply_text(
            "🎨 Choisis une couleur pour ton QR code :",
            reply_markup=color_menu_keyboard()
        )

    elif data.startswith("color_"):
        context.user_data["qr_color"] = COLOR_MAP[data]
        await query.message.reply_text(
            "Souhaites-tu des coins arrondis ?",
            reply_markup=rounded_option_keyboard(False)
        )

    elif data == "toggle_rounded":
        context.user_data["qr_rounded"] = not context.user_data.get("qr_rounded", False)
        await query.message.edit_reply_markup(
            reply_markup=rounded_option_keyboard(context.user_data["qr_rounded"])
        )

    elif data == "style_done":
        await query.message.reply_text(
            "✏️ Envoie maintenant le contenu à transformer en QR.",
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

# ================= QR CORE =================
def generate_custom_qr(data: str, color: tuple, rounded: bool) -> BytesIO:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    drawer = RoundedModuleDrawer() if rounded else SquareModuleDrawer()

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=SolidFillColorMask(
            back_color=(255, 255, 255),
            front_color=color
        ),
    )

    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio

# ================= QR IMAGE BASE64 =================
def image_to_qr_base64(image_bytes: bytes, color, rounded) -> BytesIO:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((128, 128))

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode()

    if len(encoded) > 2500:
        raise ValueError("Image trop lourde pour un QR")

    return generate_custom_qr(encoded, color, rounded)

# ================= DECODE =================
def decode_qr_from_image_bytes(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return [data] if data else []

# ================= HANDLERS =================
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if mode == "gen_text":
        qr = generate_custom_qr(
            update.message.text,
            context.user_data["qr_color"],
            context.user_data["qr_rounded"]
        )
        qr.name = "qrcode.png"
        await update.message.reply_photo(photo=qr)

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

    if mode == "gen_img_base64":
        qr = image_to_qr_base64(
            image_bytes,
            context.user_data["qr_color"],
            context.user_data["qr_rounded"]
        )

    elif mode == "gen_img_styled":
        qr = generate_custom_qr(
            "QR Stylisé",
            context.user_data["qr_color"],
            context.user_data["qr_rounded"]
        )
        logo = Image.open(BytesIO(image_bytes)).convert("RGBA")
        logo.thumbnail((200, 200))
        img = Image.open(qr)
        pos = ((img.width - logo.width) // 2, (img.height - logo.height) // 2)
        img.paste(logo, pos, logo)
        qr = BytesIO()
        img.save(qr, format="PNG")
        qr.seek(0)

    elif mode == "gen_img_link":
        qr = generate_custom_qr(
            "https://example.com/image",
            context.user_data["qr_color"],
            context.user_data["qr_rounded"]
        )

    elif mode == "decode":
        decoded = decode_qr_from_image_bytes(image_bytes)
        await update.message.reply_text(
            decoded[0] if decoded else "❌ Aucun QR détecté."
        )
        return

    else:
        return

    qr.name = "qrcode.png"
    await update.message.reply_photo(photo=qr)

# ================= UNKNOWN =================
async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commande inconnue. /start",
        reply_markup=main_menu_keyboard()
    )

# ================= MAIN =================
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
