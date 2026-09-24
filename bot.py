import asyncio
from io import BytesIO
from PIL import Image

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile

# --- Налаштування бота ---
TOKEN = "8994270807:AAE9vOINq0TMScwf6p5tc-CzzuSGOIYpW4s" # Вставте сюди ваш токен
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Стани (FSM) ---
class PDFBuilder(StatesGroup):
    waiting_for_photos = State()
    waiting_for_name = State()

# --- Клавіатури ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🖼 Створити PDF")]],
        resize_keyboard=True
    )

def finish_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Готово (Задати назву)")],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True
    )

# --- Обробники команд ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привіт! Я бот, який робить PDF з фотографій.\nНатисніть кнопку нижче, щоб розпочати.",
        reply_markup=main_menu()
    )

@dp.message(F.text == "❌ Скасувати")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Дію скасовано.", reply_markup=main_menu())

@dp.message(F.text == "🖼 Створити PDF")
async def start_pdf_creation(message: Message, state: FSMContext):
    await state.set_state(PDFBuilder.waiting_for_photos)
    await state.update_data(photos=[])
    await message.answer(
        "Відправляйте мені фотографії (можна по одній або альбомом).\n"
        "Коли закінчите, натисніть «✅ Готово».",
        reply_markup=finish_menu()
    )

@dp.message(PDFBuilder.waiting_for_photos, F.photo)
async def collect_photos(message: Message, state: FSMContext):
    # Отримуємо найвищу якість фото (останній елемент масиву)
    photo_id = message.photo[-1].file_id
    
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(photo_id)
    
    await state.update_data(photos=photos)
    # Відповідаємо тихо, щоб не спамити під час відправки альбому
    # Можна розкоментувати рядок нижче, якщо хочете отримувати сповіщення на кожне фото:
    # await message.answer(f"Фото додано! Всього: {len(photos)}")

@dp.message(PDFBuilder.waiting_for_photos, F.text == "✅ Готово (Задати назву)")
async def request_filename(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if not photos:
        await message.answer("Ви не надіслали жодного фото! Спробуйте ще раз або натисніть «Скасувати».")
        return
        
    await state.set_state(PDFBuilder.waiting_for_name)
    await message.answer(
        f"Отримано фото: {len(photos)} шт.\nТепер напишіть бажану назву для PDF файлу (наприклад: *My_Photos*):",
        parse_mode="Markdown"
    )

@dp.message(PDFBuilder.waiting_for_name, F.text)
async def generate_and_send_pdf(message: Message, state: FSMContext):
    file_name = message.text.strip()
    # Додаємо розширення, якщо його немає
    if not file_name.lower().endswith(".pdf"):
        file_name += ".pdf"
        
    data = await state.get_data()
    photo_ids = data.get("photos", [])
    
    msg_status = await message.answer("⏳ Обробка зображень та створення PDF... Зачекайте хвилинку.")
    
    images = []
    try:
        # Завантажуємо кожне фото в пам'ять
        for file_id in photo_ids:
            file_info = await bot.get_file(file_id)
            img_bytes = BytesIO()
            await bot.download_file(file_info.file_path, img_bytes)
            
            # Конвертуємо у RGB (бо PDF не підтримує альфа-канал RGBA напряму)
            img = Image.open(img_bytes).convert("RGB")
            images.append(img)
            
        # Створюємо PDF у пам'яті
        pdf_bytes = BytesIO()
        images[0].save(
            pdf_bytes, 
            format="PDF", 
            save_all=True, 
            append_images=images[1:]
        )
        pdf_bytes.seek(0)
        
        # Відправляємо готовий документ
        document = BufferedInputFile(pdf_bytes.read(), filename=file_name)
        await message.answer_document(
            document, 
            caption=f"Ось ваш файл: {file_name}",
            reply_markup=main_menu()
        )
        
    except Exception as e:
        await message.answer(f"Виникла помилка при створенні PDF: {e}", reply_markup=main_menu())
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
    # Render передає порт через змінну середовища PORT (за замовчуванням 8080)
    import os
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server() # запускаємо пінговий сервер
    print("Бот запущений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())