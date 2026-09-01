import random
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# Список фактов про игры, киберспортивные турниры и программирование
FACTS = [
    "Первой видеоигрой, побывавшей в космосе, стала Game Boy с игрой Star Wars — её взял с собой космонавт Александр Серебров в 1993 году.",
    "Самый крупный призовой фонд в истории киберспорта был разыгран на турнире The International 2021 по Dota 2 — он составил более 40 миллионов долларов.",
    "Первый компьютерный баг (bug) был реальным насекомым: мотылёк застрял в реле компьютера Harvard Mark II в 1947 году.",
    "Язык программирования Python назван не в честь рептилии, а в честь британского комик-шоу «Летающий цирк Монти Пайтона».",
    "Самым продаваемым киберспортивным турниром по просмотрам на пике стал Чемпионат мира по League of Legends (Worlds 2023) — за финалом одновременно следили более 6,4 млн человек.",
]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    welcome_text = (
        "Привет! 👋 Я бот, который знает интересные факты.\n\n"
        "Отправь мне любое сообщение, и я поделюсь фактом о видеоиграх, "
        "киберспортивных турнирах или программировании!"
    )
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    help_text = (
        "📜 **Доступные команды:**\n"
        "/start — Перезапустить бота и получить приветствие\n"
        "/help — Показать список команд\n\n"
        "💬 Напишите любое текстовое сообщение, чтобы получить случайный факт!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех обычных текстовых сообщений."""
    # Выбираем случайный факт из списка
    random_fact = random.choice(FACTS)
    await update.message.reply_text(f"💡 **Факт:** {random_fact}", parse_mode="Markdown")


def main():
    """Запуск бота."""
    # Вставьте ваш API-токен от BotFather вместо 'YOUR_TELEGRAM_BOT_TOKEN'
    TOKEN = "8823945995:AAGxtAYXRjJwAWRoXwnZViJpSTiw9zfdprQ"

    # Создаём приложение бота
    app = ApplicationBuilder().token(TOKEN).build()

    # Регистрируем хэндлеры для команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # Регистрируем хэндлер для всех остальных текстовых сообщений (исключая команды)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Запускаем бота в режиме polling
    print("Бот успешно запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()