import os
import re
import io
import sys
import logging
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CallbackContext
from PIL import Image, ImageEnhance

# -------------------- কনফিগারেশন --------------------
BOT_TOKEN = os.environ.get("8580993278:AAGaAkwu6L3JPwhQnwzHPl-RXBaAIRNPx3M", "")
MESSAGE_TIMEOUT = 120  # 2 minutes

# লগিং
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- Tesseract সেটআপ --------------------
def check_and_install_tesseract():
    """Tesseract চেক এবং ইনস্টল"""
    try:
        # Tesseract পাথ সেট
        tesseract_path = '/usr/bin/tesseract'
        
        # Tesseract ইনস্টল করা আছে কিনা চেক
        try:
            subprocess.run([tesseract_path, '--version'], 
                         capture_output=True, check=True)
            logger.info("✅ Tesseract is installed")
            return tesseract_path
        except:
            logger.info("📦 Installing Tesseract...")
            # Render.com (Ubuntu) এর জন্য
            subprocess.run(['apt-get', 'update'], capture_output=True)
            subprocess.run(['apt-get', 'install', '-y', 'tesseract-ocr'], 
                         capture_output=True)
            logger.info("✅ Tesseract installed")
            return tesseract_path
    except Exception as e:
        logger.error(f"Tesseract setup error: {e}")
        return '/usr/bin/tesseract'  # ডিফল্ট পাথ

# Tesseract সেটআপ
tesseract_path = check_and_install_tesseract()

# pytesseract ইমপোর্ট এবং কনফিগার
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    logger.info(f"✅ Tesseract configured at: {tesseract_path}")
except ImportError:
    logger.error("❌ pytesseract not installed!")
    sys.exit(1)

# -------------------- ইমেজ প্রসেসিং --------------------
def process_image(image_bytes):
    """ইমেজ প্রিপ্রসেসিং"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # গ্রেস্কেলে কনভার্ট
        if img.mode != 'L':
            img = img.convert('L')
        
        # কনট্রাস্ট বাড়ানো
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # রেজোল্যুশন ঠিক করা
        width, height = img.size
        if width < 300 or height < 300:
            img = img.resize((width*2, height*2), Image.Resampling.LANCZOS)
        
        return img
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        return None

# -------------------- নাম্বার এক্সট্র্যাক্ট --------------------
def extract_numbers_from_image(image_bytes):
    """ইমেজ থেকে শুধু নাম্বার এক্সট্র্যাক্ট"""
    try:
        # ইমেজ প্রসেস
        img = process_image(image_bytes)
        if img is None:
            return []
        
        # OCR - শুধু ইংরেজি
        text = pytesseract.image_to_string(img, lang='eng')
        
        # নাম্বার খোঁজার প্যাটার্ন (শুধু 0-9)
        patterns = [
            r'01[3-9]\d{8}',  # বাংলাদেশ: 01XXXXXXXXX
            r'\+8801[3-9]\d{8}',  # +8801XXXXXXXXX
            r'\(\d{3}\) \d{3}-\d{4}',  # (123) 456-7890
            r'\d{3}-\d{3}-\d{4}',  # 123-456-7890
            r'\b\d{10}\b',  # 10 ডিজিট
            r'\b\d{11}\b',  # 11 ডিজিট
            r'\+\d{11,14}',  # আন্তর্জাতিক +XXXXXXXXXXXX
            r'\d{3} \d{3} \d{4}',  # 123 456 7890
            r'\d{4} \d{3} \d{3}',  # 1234 567 890
        ]
        
        all_numbers = []
        seen = set()
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for num in matches:
                # শুধু ডিজিট এবং + চিহ্ন রাখা
                clean_num = re.sub(r'[^\d\+]', '', num)
                
                # ৮ ডিজিটের বেশি হওয়া লাগবে
                if len(clean_num) >= 8 and clean_num not in seen:
                    seen.add(clean_num)
                    all_numbers.append(num)
        
        return all_numbers
        
    except Exception as e:
        logger.error(f"Error extracting numbers: {e}")
        return []

# -------------------- বট হ্যান্ডলার --------------------
async def handle_photo(update: Update, context: CallbackContext):
    """ফটো মেসেজ হ্যান্ডলার"""
    try:
        chat_id = update.effective_chat.id
        
        # প্রসেসিং মেসেজ
        processing_msg = await update.message.reply_text("🔄")
        
        # ইমেজ ডাউনলোড
        photo = await update.message.photo[-1].get_file()
        image_bytes = await photo.download_as_bytearray()
        
        # নাম্বার এক্সট্র্যাক্ট
        numbers = extract_numbers_from_image(image_bytes)
        
        # প্রসেসিং মেসেজ ডিলিট
        try:
            await processing_msg.delete()
        except:
            pass
        
        if numbers:
            # ইনলাইন কিবোর্ড তৈরি
            keyboard = []
            
            for i, num in enumerate(numbers[:10]):
                # শুধু ডিজিট বের করা
                clean_num = re.sub(r'[^\d\+]', '', num)
                
                # বাটন টেক্সট
                btn_text = f"{i+1}. {num}"
                if len(num) > 15:
                    btn_text = f"{i+1}. {num[:12]}..."
                
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
            # নো নাম্বার ফাউন্ড
            sent_msg = await update.message.reply_text("❌")
        
        # ২ মিনিট পর ডিলিট
        async def delete_messages():
            await asyncio.sleep(MESSAGE_TIMEOUT)
            try:
                await sent_msg.delete()
                await update.message.delete()
            except:
                pass
        
        asyncio.create_task(delete_messages())
        
    except Exception as e:
        logger.error(f"Photo handler error: {e}")

async def handle_button(update: Update, context: CallbackContext):
    """বাটন ক্লিক হ্যান্ডলার"""
    try:
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("copy_"):
            number = query.data.replace("copy_", "")
            
            # কপি করার জন্য মেসেজ
            copy_msg = await query.edit_message_text(
                f"`{number}`",
                parse_mode='Markdown'
            )
            
            # ২ মিনিট পর ডিলিট
            async def delete_msg():
                await asyncio.sleep(MESSAGE_TIMEOUT)
                try:
                    await copy_msg.delete()
                except:
                    pass
            
            asyncio.create_task(delete_msg())
            
    except Exception as e:
        logger.error(f"Button handler error: {e}")

async def handle_text(update: Update, context: CallbackContext):
    """টেক্সট মেসেজ হ্যান্ডলার"""
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

# -------------------- মেইন ফাংশন --------------------
def main():
    """বট চালু"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set")
        logger.error("Please set BOT_TOKEN environment variable")
        sys.exit(1)
    
    try:
        # অ্যাপ্লিকেশন
        app = Application.builder().token(BOT_TOKEN).build()
        
        # হ্যান্ডলার
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.TEXT, handle_text))
        app.add_handler(CallbackQueryHandler(handle_button))
        
        # বট চালু
        logger.info("🤖 Bot starting...")
        logger.info(f"⏰ Auto-delete: {MESSAGE_TIMEOUT} seconds")
        logger.info("✅ Ready to scan numbers")
        
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == "__main__":
    main()
