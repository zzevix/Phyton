import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Списки фактов для каждой категории
GAMES_FACTS = [
    "🎮 Самая продаваемая видеоигра в истории — Minecraft (свыше 300 млн копий).",
    "🕹️ Дизайн Пакмана был вдохновлён формой пиццы с вырезанным кусочком.",
    "👾 Первой видеоигрой, побывавшей в космосе, стала StarCraft в 1999 году.",
]

PROGRAMMING_FACTS = [
    "🐍 Язык Python назван в честь британского шоу «Летающий цирк Монти Пайтона», а не змеи.",
    "🐛 Первый компьютерный «баг» — это реальный мотылёк, застрявший в реле компьютера в 1947 году.",
    "👩‍💻 Первым программистом в истории считается Ада Лавлейс (1843 год).",
]

COMPUTER_FACTS = [
    "🖱️ Первая компьютерная мышь была создана Дугласом Энгельбартом в 1964 году и была из дерева.",
    "🌐 Первый в мире веб-сайт (info.cern.ch) был запущен в 1991 году и доступен до сих пор.",
    "💾 Бортовой компьютер «Аполлона-11» имел всего 64 КБ оперативной памяти.",
]


# Функция для создания клавиатуры (чтобы не дублировать код)
def get_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Игры", callback_data="games")],
        [InlineKeyboardButton("Программирование", callback_data="programming")],
        [InlineKeyboardButton("Компьютер", callback_data="computer")],
    ]
    return InlineKeyboardMarkup(keyboard)


# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Отправка сообщения с 3 inline-кнопками
    await update.message.reply_text(
        "Выберите интересующую тему:", reply_markup=get_keyboard()
    )


# Обработчик нажатий на кнопки
async def button_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query

    # Подтверждаем получение callback
    await query.answer()

    # Ветвление if/elif/else по query.data со случайным выбором факта
    if query.data == "games":
        text = random.choice(GAMES_FACTS)
    elif query.data == "programming":
        text = random.choice(PROGRAMMING_FACTS)
    elif query.data == "computer":
        text = random.choice(COMPUTER_FACTS)
    else:
        text = "Не понял команду 🤷"

    # Редактируем текст и оставляем меню (reply_markup=get_keyboard())
    await query.edit_message_text(text=text, reply_markup=get_keyboard())


def main() -> None:
    # Вставьте токен вашего бота
    TOKEN = "8823945995:AAGxtAYXRjJwAWRoXwnZViJpSTiw9zfdprQ"

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()


if __name__ == "__main__":
    main()