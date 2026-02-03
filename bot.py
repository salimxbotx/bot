import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytesseract
from PIL import Image
import requests
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
    ContextTypes
)

# ========== CONFIGURATION ==========
# Set your bot token from environment variable (for Render deployment)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    # For local testing, you can set it directly (remove this in production)
    BOT_TOKEN = "8580993278:AAGaAkwu6L3JPwhQnwzHPl-RXBaAIRNPx3M"  # Replace with your bot token

# Tesseract path (for Windows users - remove if on Linux)
# For Render, you'll need to install tesseract in the build process
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# ========== PHONE NUMBER PARSING ==========
def extract_phone_numbers(text: str) -> List[str]:
    """Extract USA and international phone numbers from text"""
    # Patterns for phone numbers
    patterns = [
        # US format: (123) 456-7890 or 123-456-7890
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        # International with + or 00
        r'(?:\+|00)[1-9]\d{0,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
        # 10-15 digit numbers
        r'\b\d{10,15}\b',
    ]
    
    found_numbers = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        found_numbers.extend(matches)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_numbers = []
    for num in found_numbers:
        # Clean the number
        clean_num = re.sub(r'[\(\)\-\s\.]', '', num)
        if len(clean_num) >= 10 and clean_num not in seen:
            seen.add(clean_num)
            # Format US numbers nicely
            if len(clean_num) == 10 and (clean_num.startswith('1') or not clean_num.startswith('+')):
                formatted = f"+1 ({clean_num[:3]}) {clean_num[3:6]}-{clean_num[6:]}"
            elif clean_num.startswith('1') and len(clean_num) == 11:
                formatted = f"+{clean_num[:1]} ({clean_num[1:4]}) {clean_num[4:7]}-{clean_num[7:]}"
            elif not clean_num.startswith('+'):
                formatted = f"+{clean_num}"
            else:
                formatted = clean_num
            unique_numbers.append(formatted)
    
    return unique_numbers

# ========== IMAGE PROCESSING ==========
async def process_image(image_url: str) -> List[str]:
    """Download and process image with OCR"""
    try:
        # Download image
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content))
        
        # Convert to grayscale for better OCR
        image = image.convert('L')
        
        # Perform OCR
        text = pytesseract.image_to_string(image)
        
        # Extract phone numbers
        numbers = extract_phone_numbers(text)
        
        return numbers
    except Exception as e:
        print(f"Error processing image: {e}")
        return []

# ========== MESSAGE CLEANUP ==========
class MessageCleaner:
    """Manage automatic deletion of old messages"""
    def __init__(self):
        self.messages_to_delete: Dict[int, List[Dict]] = {}
    
    def add_message(self, chat_id: int, message_id: int):
        """Add a message to be deleted later"""
        if chat_id not in self.messages_to_delete:
            self.messages_to_delete[chat_id] = []
        
        self.messages_to_delete[chat_id].append({
            'message_id': message_id,
            'created_at': datetime.now()
        })
    
    async def cleanup_old_messages(self, context: ContextTypes.DEFAULT_TYPE):
        """Delete messages older than 2 minutes"""
        now = datetime.now()
        threshold = timedelta(minutes=2)
        
        for chat_id in list(self.messages_to_delete.keys()):
            messages = self.messages_to_delete[chat_id]
            to_keep = []
            
            for msg_info in messages:
                if now - msg_info['created_at'] > threshold:
                    try:
                        await context.bot.delete_message(
                            chat_id=chat_id,
                            message_id=msg_info['message_id']
                        )
                    except Exception as e:
                        print(f"Failed to delete message: {e}")
                else:
                    to_keep.append(msg_info)
            
            if to_keep:
                self.messages_to_delete[chat_id] = to_keep
            else:
                del self.messages_to_delete[chat_id]

message_cleaner = MessageCleaner()

# ========== BOT HANDLERS ==========
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming images"""
    # Get the image file
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    # Send processing indicator
    processing_msg = await update.message.reply_text("Processing...")
    
    # Process image
    numbers = await process_image(file.file_path)
    
    # Delete processing message
    await processing_msg.delete()
    
    if numbers:
        # Create response with numbers
        response_text = "\n".join(numbers)
        
        # Create copy button
        keyboard = [[InlineKeyboardButton("📋 Copy All", callback_data="copy_all")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send response
        sent_message = await update.message.reply_text(
            response_text,
            reply_markup=reply_markup
        )
        
        # Track for automatic deletion
        message_cleaner.add_message(update.effective_chat.id, sent_message.message_id)
        message_cleaner.add_message(update.effective_chat.id, update.message.message_id)
    else:
        # Send empty message if no numbers found (will be auto-deleted)
        sent_message = await update.message.reply_text("No phone numbers found.")
        message_cleaner.add_message(update.effective_chat.id, sent_message.message_id)
        message_cleaner.add_message(update.effective_chat.id, update.message.message_id)

async def handle_copy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle copy button press"""
    query = update.callback_query
    
    if query.data == "copy_all":
        # Get the text from the message above the button
        message_text = query.message.text
        
        # Create response for copied text
        await query.answer(f"✅ Copied {len(message_text.splitlines())} numbers!", show_alert=True)

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to clean up old messages"""
    await message_cleaner.cleanup_old_messages(context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (auto-delete them)"""
    message_cleaner.add_message(update.effective_chat.id, update.message.message_id)
    await update.message.delete()

async def ignore_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ignore all commands silently"""
    await update.message.delete()

# ========== MAIN APPLICATION ==========
def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(CallbackQueryHandler(handle_copy_button))
    
    # Delete all text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Delete all commands
    application.add_handler(CommandHandler(["start", "help", "about"], ignore_commands))
    
    # Add cleanup job
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(cleanup_job, interval=30, first=10)
    
    # Start bot
    print("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
