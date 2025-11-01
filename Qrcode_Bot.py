#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QRcodeBot - Bot Telegram pour générer et décoder des QR codes.
Version sécurisée avec lecture du token depuis .env
"""

import logging
import os
from io import BytesIO

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

# --- Chargement du token depuis .env ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Vérification ---
if not BOT_TOKEN:
    raise ValueError("❌ Erreur : Le token du bot est introuvable. "
                     "Assure-toi d'avoir créé un fichier .env avec la ligne :\nBOT_TOKEN=ton_token_ici")

# --- Configuration du logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- UI Helpers ---
def main_menu_keyboard():
    """Menu principal"""
    keyboard = [
        [InlineKeyboardButton("🌀 Générer un QR code", callback_data="mode_generate")],
        [InlineKeyboardButton("🔍 Décoder un QR code", callback_data="mode_decode")],
    ]
    return InlineKeyboardMarkup(keyboard)


def in_mode_keyboard():
    """Menu secondaire (pendant génération ou décodage)"""
    keyboard = [
        [InlineKeyboardButton("⬅️ Retour au menu", callback_data="back_to_menu")],
        [InlineKeyboardButton("🛑 Arrêter (/stop)", callback_data="stop")],
    ]
    return InlineKeyboardMarkup(keyboard)


# --- Commandes principales ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.effective_user
    text = (
        f"👋 Bonjour {user.first_name or 'utilisateur'} !\n\n"
        "Je suis *QRcodeBot*, ton assistant pour créer et lire des QR codes.\n\n"
        "Que veux-tu faire ?"
    )
    context.user_data['mode'] = None
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /stop"""
    context.user_data['mode'] = None
    await update.message.reply_text("🛑 Mode arrêté. Retour au menu principal.", reply_markup=main_menu_keyboard())


# --- Gestion des boutons du menu ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "mode_generate":
        context.user_data['mode'] = 'generate'
        await query.message.reply_text(
            "🌀 Mode *Génération* activé.\n"
            "Envoie-moi le texte ou le lien à transformer en QR code.\n\n"
            "Tu peux en envoyer plusieurs sans revenir au menu.",
            parse_mode="Markdown",
            reply_markup=in_mode_keyboard()
        )

    elif data == "mode_decode":
        context.user_data['mode'] = 'decode'
        await query.message.reply_text(
            "🔍 Mode *Décodage* activé.\n"
            "Envoie-moi une image (photo ou fichier) contenant un QR code à lire.\n\n"
            "Tu peux en envoyer plusieurs successivement.",
            parse_mode="Markdown",
            reply_markup=in_mode_keyboard()
        )

    elif data == "back_to_menu":
        context.user_data['mode'] = None
        await query.message.reply_text("⬅️ Retour au menu principal.", reply_markup=main_menu_keyboard())

    elif data == "stop":
        context.user_data['mode'] = None
        await query.message.reply_text("🛑 Mode arrêté. Tape /start pour recommencer.", reply_markup=main_menu_keyboard())


# --- Génération de QR ---
def generate_qr_image_bytes(text: str) -> BytesIO:
    """Crée un QR code PNG en mémoire"""
    qr = qrcode.QRCode(
        version=None,
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


# --- Décodage de QR ---
def decode_qr_from_image_bytes(image_bytes: bytes):
    """Tente de décoder un QR code depuis une image (OpenCV)"""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)
    if data:
        return [data]

    try:
        retval, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
        if retval:
            return [d for d in decoded_info if d]
    except Exception:
        pass

    return []


# --- Messages texte ---
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    text = update.message.text.strip() if update.message.text else ""

    if mode == 'generate':
        if not text:
            await update.message.reply_text("⚠️ Envoie un texte ou un lien à transformer en QR code.")
            return

        bio = generate_qr_image_bytes(text)
        bio.name = "qrcode.png"
        await update.message.reply_photo(
            photo=bio,
            caption="✅ Voici ton QR code.\nEnvoie un autre texte pour en générer un autre, ou /stop pour quitter."
        )

    else:
        await update.message.reply_text("❔ Choisis une action dans le menu :", reply_markup=main_menu_keyboard())


# --- Messages avec images ---
async def photo_or_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    file_id = None

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type.startswith("image/"):
        file_id = update.message.document.file_id

    if not file_id:
        await update.message.reply_text("⚠️ Envoie une photo ou un fichier image contenant un QR code.")
        return

    if mode == 'decode':
        file = await context.bot.get_file(file_id)
        bio = BytesIO()
        await file.download_to_memory(out=bio)
        bio.seek(0)
        decoded_list = decode_qr_from_image_bytes(bio.getvalue())

        if not decoded_list:
            await update.message.reply_text("❌ Aucun QR code détecté. Essaie une image plus nette.")
        elif len(decoded_list) == 1:
            await update.message.reply_text(f"📜 Contenu décodé :\n\n{decoded_list[0]}")
        else:
            await update.message.reply_text("📜 Plusieurs QR codes trouvés :\n" + "\n".join(decoded_list))
    else:
        await update.message.reply_text("💡 Tu dois d'abord choisir *Décoder un QR code* dans le menu.", reply_markup=main_menu_keyboard())


# --- Messages inconnus ---
async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Je n'ai pas compris. Utilise /start pour revenir au menu.")


# --- Main ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_command))

    # Boutons
    app.add_handler(CallbackQueryHandler(button_callback))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_or_document_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE, photo_or_document_handler))

    # Fallback
    app.add_handler(MessageHandler(filters.ALL, unknown_handler))

    logger.info("✅ QRcodeBot démarré (mode polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
