import json
import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import os
from dotenv import load_dotenv

# Находим и загружаем файл .env
load_dotenv()

# Извлекаем токен
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Проверка, что токен успешно прочитан
if not BOT_TOKEN:
    raise ValueError("Ошибка: Токен не найден в файле .env!")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Состояния для ConversationHandler
NAME, COLOR, CAR = range(3)

# Глобальный словарь для хранения профилей пользователей
user_data = {}


def load_data() -> None:
    """Загружает данные из user.json при запуске приложения."""
    global user_data
    if os.path.exists("user.json"):
        try:
            with open("user.json", "r", encoding="utf-8") as f:
                user_data = json.load(f)
            logging.info("Данные загружены из user.json")
        except Exception as e:
            logging.error(f"Ошибка загрузки: {e}")
            user_data = {}


def save_data() -> None:
    """Сохраняет текущий словарь user_data в файл user.json."""
    try:
        with open("user.json", "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        logging.info("Данные сохранены в user.json")
    except Exception as e:
        logging.error(f"Ошибка сохранения: {e}")


def get_profile_text(user_id: str) -> str:
    """Вспомогательная функция для формирования текста профиля."""
    if user_id in user_data:
        profile = user_data[user_id]
        return (
            f"📋 Ваш профиль:\n\n"
            f"👤 Имя: {profile.get('name', 'Не указано')}\n"
            f"🎨 Цвет: {profile.get('color', 'Не указан')}\n"
            f"🚘 Машина: {profile.get('car', 'Не указана')}"
        )
    return "❌ Профиль не найден. Нажмите /start, чтобы пройти опрос!"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 1: Запрос имени текстом."""
    await update.message.reply_text(
        "Привет! Давайте зайдём в Ваш профиль.\nКак Вас зовут?"
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 2: Получение имени и отправка Inline-кнопок для выбора цвета."""
    name = update.message.text
    context.user_data["name"] = name

    # 3 Inline-кнопки для выбора цвета
    keyboard = [
        [
            InlineKeyboardButton("🔴 Красный", callback_data="color_Красный"),
            InlineKeyboardButton("🔵 Синий", callback_data="color_Синий"),
            InlineKeyboardButton("🟢 Зелёный", callback_data="color_Зелёный"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Приятно познакомиться, {name}! Выберите Ваш любимый цвет:",
        reply_markup=reply_markup,
    )
    return COLOR


async def get_color_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 3: Сохранение цвета и отправка Inline-кнопок для выбора машины."""
    query = update.callback_query
    await query.answer()

    chosen_color = query.data.split("_")[1]
    context.user_data["color"] = chosen_color

    # 3 Inline-кнопки для выбора машины
    keyboard = [
        [
            InlineKeyboardButton("🚗 BMW", callback_data="car_BMW"),
            InlineKeyboardButton("🏎 Audi", callback_data="car_Audi"),
            InlineKeyboardButton("🚙 Mercedes", callback_data="car_Mercedes"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"Выбран цвет: {chosen_color}.\nТеперь выберите любимую марку машины:",
        reply_markup=reply_markup,
    )
    return CAR


async def get_car_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 4: Сохранение машины, запись в JSON и выгрузка кнопки просмотра профиля."""
    query = update.callback_query
    await query.answer()

    chosen_car = query.data.split("_")[1]
    user_id = str(update.effective_user.id)

    name = context.user_data.get("name")
    color = context.user_data.get("color")

    # Сохраняем все 3 параметра в глобальный словарь
    user_data[user_id] = {
        "name": name,
        "color": color,
        "car": chosen_car,
    }

    # Сохраняем в user.json
    save_data()

    # Кнопка для быстрого вызова профиля
    keyboard = [[InlineKeyboardButton("📱 Посмотреть профиль", callback_data="show_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="Отлично! Все данные успешно сохранены в JSON.",
        reply_markup=reply_markup,
    )
    return ConversationHandler.END


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /profile: Отправляет Inline-кнопку для показа профиля."""
    keyboard = [[InlineKeyboardButton("🔍 Показать мой профиль", callback_data="show_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Нажмите на кнопку ниже, чтобы увидеть сохранённые данные:",
        reply_markup=reply_markup,
    )


async def show_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик Inline-кнопки вывода профиля."""
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    text = get_profile_text(user_id)

    # Редактируем сообщение или отправляем текст профиля
    await query.edit_message_text(text=text)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога."""
    await update.message.reply_text("Заполнение профиля отменено.")
    return ConversationHandler.END


def main():
    # Загружаем сохраненный user.json
    load_data()


# ================= TOKEN =================

    BOT_TOKEN = os.environ.get ('BOT_TOKEN')

    app = Application.builder().token(BOT_TOKEN).build()

    # Диалог опроса
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            COLOR: [CallbackQueryHandler(get_color_callback, pattern="^color_")],
            CAR: [CallbackQueryHandler(get_car_callback, pattern="^car_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    
    # Команда /profile и обработчик Inline-кнопки профиля
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CallbackQueryHandler(show_profile_callback, pattern="^show_profile$"))

    app.run_polling()


if __name__ == "__main__":
    main()