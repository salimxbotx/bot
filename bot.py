import os
import re
import io
import sys
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CallbackContext
from PIL import Image, ImageEnhance
import pytesseract

# -------------------- কনফিগারেশন --------------------
BOT_TOKEN = os.environ.get("8580993278:AAGaAkwu6L3JPwhQnwzHPl-RXBaAIRNPx3M", "")
MESSAGE_TIMEOUT = 120  # 2 minutes

# লগিং
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Tesseract পাথ
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

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
    except:
        return Image.open(io.BytesIO(image_bytes))

# -------------------- নাম্বার এক্সট্র্যাক্ট --------------------
def extract_numbers_from_image(image_bytes):
    """ইমেজ থেকে শুধু নাম্বার এক্সট্র্যাক্ট"""
    try:
        # ইমেজ প্রসেস
        img = process_image(image_bytes)
        
        # OCR - শুধু ইংরেজি
        text = pytesseract.image_to_string(img, lang='eng')
        
        # শুধু 0-9 সংখ্যা খোঁজা (বাংলা সংখ্যা নয়)
        # প্যাটার্ন ১: 01XXXXXXXXX (বাংলাদেশ)
        pattern1 = r'01[3-9]\d{8}'
        matches1 = re.findall(pattern1, text)
        
        # প্যাটার্ন ২: +8801XXXXXXXXX
        pattern2 = r'\+8801[3-9]\d{8}'
        matches2 = re.findall(pattern2, text)
        
        # প্যাটার্ন ৩: (XXX) XXX-XXXX
        pattern3 = r'\(\d{3}\) \d{3}-\d{4}'
        matches3 = re.findall(pattern3, text)
        
        # প্যাটার্ন ৪: XXX-XXX-XXXX
        pattern4 = r'\d{3}-\d{3}-\d{4}'
        matches4 = re.findall(pattern4, text)
        
        # প্যাটার্ন ৫: XXXXXXXXXX (10 ডিজিট)
        pattern5 = r'\b\d{10}\b'
        matches5 = re.findall(pattern5, text)
        
        # প্যাটার্ন ৬: XXXXXXXXXXX (11 ডিজিট)
        pattern6 = r'\b\d{11}\b'
        matches6 = re.findall(pattern6, text)
        
        # প্যাটার্ন ৭: +XXXXXXXXXXXX (আন্তর্জাতিক)
        pattern7 = r'\+\d{11,14}'
        matches7 = re.findall(pattern7, text)
        
        # প্যাটার্ন ৮: XXX XXX XXXX (স্পেস সহ)
        pattern8 = r'\d{3} \d{3} \d{4}'
        matches8 = re.findall(pattern8, text)
        
        # প্যাটার্ন ৯: XXXX XXX XXX
        pattern9 = r'\d{4} \d{3} \d{3}'
        matches9 = re.findall(pattern9, text)
        
        # সব মিলিয়ে
        all_matches = matches1 + matches2 + matches3 + matches4 + matches5 + matches6 + matches7 + matches8 + matches9
        
        # ডুপ্লিকেট রিমুভ
        unique_numbers = []
        seen = set()
        
        for num in all_matches:
            # শুধু ডিজিট এবং + চিহ্ন রাখা
            clean_num = re.sub(r'[^\d\+]', '', num)
            
            # ৮ ডিজিটের বেশি হওয়া লাগবে
            if len(clean_num) >= 8 and clean_num not in seen:
                seen.add(clean_num)
                unique_numbers.append(num)
        
        return unique_numbers
        
    except Exception as e:
        logger.error(f"Error extracting numbers: {e}")
        return []

# -------------------- বট হ্যান্ডলার --------------------
async def handle_photo(update: Update, context: CallbackContext):
    """ফটো মেসেজ হ্যান্ডলার"""
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
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
            
            for i, num in enumerate(numbers[:10]):  # সর্বোচ্চ ১০টা
                # শুধু ডিজিট বের করা
                clean_num = re.sub(r'[^\d\+]', '', num)
                
                # বাটন টেক্সট (সংক্ষিপ্ত)
                btn_text = num
                if len(num) > 15:
                    btn_text = num[:12] + "..."
                
                button = InlineKeyboardButton(
                    text=f"{i+1}. {btn_text}",
                    callback_data=f"num_{clean_num}"
                )
                keyboard.append([button])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # মেসেজ সেন্ড
            sent_msg = await update.message.reply_text(
                f"📱 Found: {len(numbers)}",
                reply_markup=reply_markup
            )
            
            # ২ মিনিট পর ডিলিট
            async def delete_msg():
                await asyncio.sleep(MESSAGE_TIMEOUT)
                try:
                    await sent_msg.delete()
                    await update.message.delete()
                except:
                    pass
            
            asyncio.create_task(delete_msg())
            
        else:
            # নো নাম্বার ফাউন্ড
            no_num_msg = await update.message.reply_text("❌")
            
            # ২ মিনিট পর ডিলিট
            async def delete_no_num():
                await asyncio.sleep(MESSAGE_TIMEOUT)
                try:
                    await no_num_msg.delete()
                    await update.message.delete()
                except:
                    pass
            
            asyncio.create_task(delete_no_num())
            
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")

async def handle_button(update: Update, context: CallbackContext):
    """বাটন ক্লিক হ্যান্ডলার"""
    try:
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("num_"):
            number = query.data.replace("num_", "")
            
            # ফরম্যাট করা
            formatted = number
            
            if len(number) == 11 and number.startswith("1"):
                formatted = f"+1 ({number[1:4]}) {number[4:7]}-{number[7:]}"
            elif len(number) == 13 and number.startswith("880"):
                formatted = f"+88 {number[3:6]}-{number[6:10]}-{number[10:]}"
            elif len(number) == 10:
                formatted = f"({number[:3]}) {number[3:6]}-{number[6:]}"
            elif len(number) == 11:
                formatted = f"({number[:4]}) {number[4:7]}-{number[7:]}"
            
            # কপি করার জন্য মেসেজ
            copy_msg = await query.edit_message_text(
                f"```{formatted}```\n📋",
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
        logger.error(f"Error in handle_button: {e}")

async def handle_text(update: Update, context: CallbackContext):
    """টেক্সট মেসেজ হ্যান্ডলার (শুধু ডিলিট)"""
    try:
        # ২ মিনিট পর টেক্সট মেসেজ ডিলিট
        async def delete_text():
            await asyncio.sleep(MESSAGE_TIMEOUT)
            try:
                await update.message.delete()
            except:
                pass
        
        asyncio.create_task(delete_text())
        
    except:
        pass

# -------------------- মেইন ফাংশন --------------------
def main():
    """বট চালু"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set")
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
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == "__main__":
    main()
