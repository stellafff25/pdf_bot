import asyncio
import re
import sqlite3

from io import BytesIO
from PIL import Image
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile

# --- Bot Settings ---
TOKEN = "8994270807:AAE9vOINq0TMScwf6p5tc-CzzuSGOIYpW4s" # Insert your token here
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- BD settings ---
ADMIN_ID = 750631739

conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY
    )
''')
conn.commit()

# --- States (FSM) ---
class PDFBuilder(StatesGroup):
    waiting_for_photos = State()
    waiting_for_name = State()

# --- Keyboards ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🖼 Create PDF")]],
        resize_keyboard=True
    )

def finish_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Done (Set name)")],
            [KeyboardButton(text="❌ Cancel")]
        ],
        resize_keyboard=True
    )

# --- Command Handlers ---
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    # Проверяем, что команду вызвал админ
    if message.from_user.id != ADMIN_ID:
        return # Если это не вы, бот просто проигнорирует команду
        
    # Считаем количество пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    await message.answer(f"📊 <b>Статистика бота:</b>\nВсего уникальных пользователей: {count}", parse_mode="HTML")
    
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    # Добавляем пользователя в базу
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    
    await message.answer(
        "Hello! I am a bot that creates PDFs from photos.\nPress the button below to start.",
        reply_markup=main_menu()
    )

@dp.message(F.text == "❌ Cancel")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Action canceled.", reply_markup=main_menu())

@dp.message(F.text == "🖼 Create PDF")
async def start_pdf_creation(message: Message, state: FSMContext):
    await state.set_state(PDFBuilder.waiting_for_photos)
    await state.update_data(photos=[])
    await message.answer(
        "Send me photos (one by one or as an album).\n"
        "When finished, press «✅ Done».",
        reply_markup=finish_menu()
    )

@dp.message(PDFBuilder.waiting_for_photos, F.photo)
async def collect_photos(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    photos = data.get("photos", [])
    # Save a dictionary: message ID for sorting and the file ID itself
    photos.append({"msg_id": message.message_id, "file_id": photo_id})
    
    await state.update_data(photos=photos)

@dp.message(PDFBuilder.waiting_for_photos, F.text == "✅ Done (Set name)")
async def request_filename(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if not photos:
        await message.answer("You haven't sent any photos! Try again or press «Cancel».")
        return
        
    await state.set_state(PDFBuilder.waiting_for_name)
    await message.answer(
        f"Received photos: {len(photos)}\nNow enter the desired name for the PDF file (e.g., *My_Photos*):",
        parse_mode="Markdown"
    )

@dp.message(PDFBuilder.waiting_for_name, F.text)
async def generate_and_send_pdf(message: Message, state: FSMContext):
    # SOLUTION 2: Replace newlines with spaces
    file_name = message.text.replace('\n', ' ').strip()
    
    # Additionally: remove characters that are forbidden in OS filenames (\, /, *, ?, ", <, >, |)
    file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
    
    # Add extension if it's missing
    if not file_name.lower().endswith(".pdf"):
        file_name += ".pdf"
        
    data = await state.get_data()
    raw_photos = data.get("photos", [])
    
    # SOLUTION 1: Sort photos by message ID to ensure strict chronological order
    raw_photos.sort(key=lambda x: x["msg_id"])
    
    # Extract only file_id from the sorted list
    photo_ids = [item["file_id"] for item in raw_photos]
    
    msg_status = await message.answer("⏳ Processing images and creating PDF... Please wait a moment.")
    
    images = []
    try:
        # Load each photo into memory (the order is now 100% correct)
        for file_id in photo_ids:
            file_info = await bot.get_file(file_id)
            img_bytes = BytesIO()
            await bot.download_file(file_info.file_path, img_bytes)
            
            img = Image.open(img_bytes).convert("RGB")
            images.append(img)
            
        # Create PDF in memory
        pdf_bytes = BytesIO()
        images[0].save(
            pdf_bytes, 
            format="PDF", 
            save_all=True, 
            append_images=images[1:]
        )
        pdf_bytes.seek(0)
        
        # Send the finished document
        document = BufferedInputFile(pdf_bytes.read(), filename=file_name)
        await message.answer_document(
            document, 
            caption=f"Here is your file: {file_name}",
            reply_markup=main_menu()
        )
        
    except Exception as e:
        await message.answer(f"An error occurred while creating the PDF: {e}", reply_markup=main_menu())
    finally:
        await bot.delete_message(chat_id=message.chat.id, message_id=msg_status.message_id)
        await state.clear()

async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render passes the port via the PORT environment variable (default is 8080)
    import os
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server() # start the ping server
    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())