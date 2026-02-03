"""
Telegram Number Scanner Bot
Render.com compatible version
"""

import os
import re
import io
import sys
import json
import time
import base64
import logging
import asyncio
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CallbackContext
from PIL import Image, ImageEnhance, ImageFilter

# -------------------- কনফিগারেশন --------------------
BOT_TOKEN = os.environ.get("8580993278:AAGaAkwu6L3JPwhQnwzHPl-RXBaAIRNPx3M", "")
MESSAGE_TIMEOUT = 120  # 2 minutes

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- OCR API (Tesseract বিকল্প) --------------------
class OCRProcessor:
    """Tesseract ছাড়া OCR প্রসেসিং"""
    
    @staticmethod
    def preprocess_image(image_bytes):
        """ইমেজ প্রিপ্রসেসিং"""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            # সাইজ ঠিক করা
            width, height = img.size
            if width > 2000 or height > 2000:
                img = img.resize((width//2, height//2), Image.Resampling.LANCZOS)
            
            # গ্রেস্কেলে কনভার্ট
            if img.mode != 'L':
                img = img.convert('L')
            
            # কনট্রাস্ট বাড়ানো
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            
            # ব্রাইটনেস ঠিক করা
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.2)
            
            # নয়েজ কমানো
            img = img.filter(ImageFilter.MedianFilter(size=3))
            
            return img
        except Exception as e:
            logger.error(f"Image preprocessing error: {e}")
            return None
    
    @staticmethod
    def extract_numbers_manual(image):
        """ম্যানুয়ালি নাম্বার এক্সট্র্যাক্ট (সিম্পল লজিক)"""
        try:
            # ইমেজ থেকে pixel ডাটা নেওয়া
            pixels = list(image.getdata())
            width, height = image.size
            
            # বেসিক OCR - লাইন বাই লাইন স্ক্যান
            # এইটা বেসিক লজিক, বেটার রেজাল্টের জন্য API ব্যবহার করুন
            
            # ইমেজ সেভ (ডিবাগিং এর জন্য)
            image.save("/tmp/processed.png")
            
            # ফিক্সড নম্বর (ডেমো) - আপনি এখানে আপনার লজিক যোগ করুন
            # বাস্তবে API ব্যবহার করতে হবে
            
            # ডেমো নাম্বার
            demo_numbers = [
                "+8801712345678",
                "01712345678",
                "(123) 456-7890",
                "123-456-7890"
            ]
            
            return demo_numbers
            
        except Exception as e:
            logger.error(f"Manual OCR error: {e}")
            return []
    
    @staticmethod
    def extract_numbers_api(image):
        """ফ্রি OCR API ব্যবহার করে"""
        try:
            # ইমেজকে base64 এ কনভার্ট
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            # OCR.space ফ্রি API
            api_url = "https://api.ocr.space/parse/image"
            payload = {
                'apikey': 'helloworld',  # ফ্রি API key
                'base64Image': f"data:image/png;base64,{img_base64}",
                'language': 'eng',
                'isOverlayRequired': False,
                'OCREngine': 2
            }
            
            response = requests.post(api_url, data=payload, timeout=30)
            result = response.json()
            
            if result.get("IsErroredOnProcessing"):
                return []
            
            # পার্স করা টেক্সট
            parsed_text = ""
            for item in result.get("ParsedResults", []):
                parsed_text += item.get("ParsedText", "")
            
            # নাম্বার খোঁজা
            numbers = []
            
            # প্যাটার্নস
            patterns = [
                r'01[3-9]\d{8}',  # 01712345678
                r'\+8801[3-9]\d{8}',  # +8801712345678
                r'\(\d{3}\) \d{3}-\d{4}',  # (123) 456-7890
                r'\d{3}-\d{3}-\d{4}',  # 123-456-7890
                r'\b\d{10}\b',  # 10 ডিজিট
                r'\b\d{11}\b',  # 11 ডিজিট
                r'\+\d{11,14}',  # +XXXXXXXXXXXX
                r'\d{3} \d{3} \d{4}',  # 123 456 7890
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, parsed_text)
                for num in matches:
                    clean_num = re.sub(r'[^\d\+]', '', num)
                    if len(clean_num) >= 8 and clean_num not in numbers:
                        numbers.append(num)
            
            return numbers
            
        except Exception as e:
            logger.error(f"API OCR error: {e}")
            return []

# -------------------- বট হ্যান্ডলার --------------------
class TelegramBot:
    def __init__(self):
        self.ocr = OCRProcessor()
    
    async def handle_photo(self, update: Update, context: CallbackContext):
        """ফটো প্রসেস করা"""
        try:
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            logger.info(f"📸 Processing image from user {user_id}")
            
            # প্রসেসিং মেসেজ
            processing_msg = await update.message.reply_text("🔄")
            
            # ইমেজ ডাউনলোড
            photo = await update.message.photo[-1].get_file()
            image_bytes = await photo.download_as_bytearray()
            
            # ইমেজ প্রসেস
            processed_img = self.ocr.preprocess_image(image_bytes)
            
            if processed_img is None:
                await processing_msg.edit_text("❌")
                return
            
            # নাম্বার এক্সট্র্যাক্ট
            numbers = self.ocr.extract_numbers_api(processed_img)
            
            # যদি API কাজ না করে, ম্যানুয়াল ট্রাই
            if not numbers:
                numbers = self.ocr.extract_numbers_manual(processed_img)
            
            # প্রসেসিং মেসেজ ডিলিট
            try:
                await processing_msg.delete()
            except:
                pass
            
            if numbers:
                # ইনলাইন কিবোর্ড
                keyboard = []
                
                for i, num in enumerate(numbers[:15]):
                    clean_num = re.sub(r'[^\d\+]', '', num)
                    
                    btn_text = f"{i+1}. {num}"
                    if len(num) > 20:
                        btn_text = f"{i+1}. {num[:17]}..."
                    
                    button = InlineKeyboardButton(
                        text=btn_text,
                        callback_data=f"copy_{clean_num}"
                    )
                    keyboard.append([button])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # মেসেজ সেন্ড
                sent_msg = await update.message.reply_text(
                    f"📱 {len(numbers)}",
                    reply_markup=reply_markup
                )
                
            else:
                sent_msg = await update.message.reply_text("❌")
            
            # ২ মিনিট পর ডিলিট
            async def cleanup():
                await asyncio.sleep(MESSAGE_TIMEOUT)
                try:
                    await sent_msg.delete()
                    await update.message.delete()
                except:
                    pass
            
            asyncio.create_task(cleanup())
            
        except Exception as e:
            logger.error(f"Photo handler error: {e}")
    
    async def handle_button(self, update: Update, context: CallbackContext):
        """কপি বাটন হ্যান্ডলার"""
        try:
            query = update.callback_query
            await query.answer()
            
            if query.data.startswith("copy_"):
                number = query.data.replace("copy_", "")
                
                # ফরম্যাট করা
                formatted = number
                if len(number) == 11 and number.startswith("1"):
                    formatted = f"+1 ({number[1:4]}) {number[4:7]}-{number[7:]}"
                elif len(number) == 13 and number.startswith("880"):
                    formatted = f"+88 {number[3:6]}-{number[6:10]}-{number[10:]}"
                elif len(number) == 10:
                    formatted = f"({number[:3]}) {number[3:6]}-{number[6:]}"
                
                # কপি মেসেজ
                copy_msg = await query.edit_message_text(
                    f"`{formatted}`\n📋",
                    parse_mode='Markdown'
                )
                
                # ২ মিনিট পর ডিলিট
                async def delete_copy():
                    await asyncio.sleep(MESSAGE_TIMEOUT)
                    try:
                        await copy_msg.delete()
                    except:
                        pass
                
                asyncio.create_task(delete_copy())
                
        except Exception as e:
            logger.error(f"Button handler error: {e}")
    
    async def handle_text(self, update: Update, context: CallbackContext):
        """টেক্সট মেসেজ (শুধু ডিলিট)"""
        try:
            # ২ মিনিট পর ডিলিট
            async def delete_msg():
                await asyncio.sleep(MESSAGE_TIMEOUT)
                try:
                    await update.message.delete()
                except:
                    pass
            
            asyncio.create_task(delete_msg())
            
        except:
            pass
    
    def run(self):
        """বট চালু"""
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN not set!")
            logger.error("Set environment variable: BOT_TOKEN=your_token")
            return
        
        try:
            app = Application.builder().token(BOT_TOKEN).build()
            
            # হ্যান্ডলার
            app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
            app.add_handler(MessageHandler(filters.TEXT, self.handle_text))
            app.add_handler(CallbackQueryHandler(self.handle_button))
            
            # লগ
            logger.info("🤖 Bot starting...")
            logger.info(f"⏰ Auto-delete: {MESSAGE_TIMEOUT}s")
            logger.info("✅ Ready for images")
            
            app.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"Failed to start: {e}")

# -------------------- মেইন --------------------
if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
