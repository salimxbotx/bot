import os
import re
import io
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    CallbackContext,
    filters,
)

from PIL import Image, ImageEnhance
import pytesseract

TOKEN = os.environ.get("8580993278:AAGaAkwu6L3JPwhQnwzHPl-RXBaAIRNPx3M", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NumberExtractorBot")


def setup_tesseract():
    paths = [
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            logger.info(f"Tesseract found at: {p}")
            return
    logger.warning("Tesseract not found in standard paths, using default")


setup_tesseract()


class NumberExtractorBot:
    def __init__(self):
        self.ttl_seconds = 120  # auto-delete after 2 minutes

        self.patterns = [
            r"\+\d{1,4}[-\s]?\(?\d{1,5}\)?[-\s]?\d{1,5}[-\s]?\d{3,10}",  # Intl
            r"01[3-9]\d[-]?\d{3}[-]?\d{4}",                              # BD
            r"01[3-9]\d{8}",                                              # BD plain
            r"\(\d{3}\)[-\s]?\d{3}[-\s]?\d{4}",                           # (xxx) xxx-xxxx
            r"\b\d{3}[-\s\.]?\d{3}[-\s\.]?\d{4}\b",                       # xxx-xxx-xxxx
            r"\+91[-\s]?\d{5}[-\s]?\d{5}",                                # India
            r"\+44[-\s]?\d{4}[-\s]?\d{6}",                                # UK
            r"\b\d{8,15}\b",                                              # long digits
        ]

    def improve_image_quality(self, image: Image.Image) -> Image.Image:
        try:
            if image.mode != "L":
                image = image.convert("L")
            image = ImageEnhance.Contrast(image).enhance(2.0)
            image = ImageEnhance.Brightness(image).enhance(1.1)
            image = ImageEnhance.Sharpness(image).enhance(1.5)
            return image
        except Exception as e:
            logger.error(f"Image improve error: {e}")
            return image

    def normalize(self, s: str) -> str:
        s = s.strip()
        s = re.sub(r"[^\d\+]", "", s)
        if "+" in s and not s.startswith("+"):
            s = s.replace("+", "")
        return s

    def extract_numbers_from_bytes(self, image_bytes: bytes) -> list[str]:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image = self.improve_image_quality(image)

            # English only
            text = pytesseract.image_to_string(image, lang="eng")

            found = []
            seen = set()

            for pat in self.patterns:
                for m in re.findall(pat, text):
                    raw = re.sub(r"\s+", " ", m).strip()
                    norm = self.normalize(raw)
                    digits = norm.replace("+", "")

                    if len(digits) < 8:
                        continue
                    if norm not in seen:
                        seen.add(norm)
                        found.append(norm)

            return found
        except Exception as e:
            logger.error(f"extract_numbers error: {e}")
            return []

    async def safe_delete(self, context: CallbackContext, chat_id: int, message_id: int):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    def schedule_delete(self, context: CallbackContext, chat_id: int, message_id: int, seconds: int | None = None):
        seconds = seconds if seconds is not None else self.ttl_seconds
        context.application.job_queue.run_once(
            callback=lambda c: c.application.create_task(self.safe_delete(c, chat_id, message_id)),
            when=seconds,
        )

    async def delete_old_bot_messages(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        old_ids = context.chat_data.get("last_bot_message_ids", [])
        for mid in old_ids:
            await self.safe_delete(context, chat_id, mid)
        context.chat_data["last_bot_message_ids"] = []

    def remember_bot_message(self, context: CallbackContext, message_id: int):
        arr = context.chat_data.get("last_bot_message_ids", [])
        arr.append(message_id)
        context.chat_data["last_bot_message_ids"] = arr[-10:]

    def build_keyboard(self, numbers: list[str]) -> InlineKeyboardMarkup:
        keyboard = []
        for i, n in enumerate(numbers[:15], 1):
            display = n if len(n) <= 22 else (n[:22] + "...")
            keyboard.append([InlineKeyboardButton(f"{i}. {display}", callback_data=f"COPY|{n}")])
        return InlineKeyboardMarkup(keyboard)

    async def handle_image(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        message = update.message

        # delete previous bot results immediately
        await self.delete_old_bot_messages(update, context)

        try:
            image_bytes = None

            if message.photo:
                f = await message.photo[-1].get_file()
                image_bytes = await f.download_as_bytearray()
            elif message.document and (message.document.mime_type or "").startswith("image/"):
                f = await message.document.get_file()
                image_bytes = await f.download_as_bytearray()

            if not image_bytes:
                # delete user message anyway
                self.schedule_delete(context, chat_id, message.message_id)
                return

            numbers = self.extract_numbers_from_bytes(image_bytes)

            # Always delete user image message
            self.schedule_delete(context, chat_id, message.message_id)

            if not numbers:
                # No extra text; just delete silently (or send nothing)
                return

            # Numbers-only message (no extra words)
            text = "\n".join(numbers)

            sent = await message.reply_text(
                text=text,
                reply_markup=self.build_keyboard(numbers),
                disable_web_page_preview=True,
            )

            self.remember_bot_message(context, sent.message_id)
            self.schedule_delete(context, chat_id, sent.message_id)

        except Exception as e:
            logger.error(f"handle_image error: {e}")
            # delete user message anyway
            self.schedule_delete(context, chat_id, message.message_id)

    async def handle_copy(self, update: Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        if not data.startswith("COPY|"):
            return

        number = data.split("|", 1)[1].strip()

        # Numbers-only response (no extra words)
        try:
            await query.edit_message_text(text=number)
        except Exception:
            msg = await query.message.reply_text(text=number)
            self.remember_bot_message(context, msg.message_id)
            self.schedule_delete(context, query.message.chat_id, msg.message_id)

        self.schedule_delete(context, query.message.chat_id, query.message.message_id)

    async def delete_any_text(self, update: Update, context: CallbackContext):
        # Bot won't talk on text. Just delete user text message.
        self.schedule_delete(context, update.effective_chat.id, update.message.message_id)

    def run(self):
        if not TOKEN:
            logger.error("BOT_TOKEN not set!")
            return

        app = Application.builder().token(TOKEN).build()

        app.add_handler(MessageHandler(filters.PHOTO, self.handle_image))
        app.add_handler(MessageHandler(filters.Document.IMAGE, self.handle_image))
        app.add_handler(CallbackQueryHandler(self.handle_copy))

        # delete any other text
        app.add_handler(MessageHandler(filters.TEXT, self.delete_any_text))

        logger.info("Bot started (English OCR, numbers-only).")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    NumberExtractorBot().run()
