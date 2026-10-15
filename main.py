import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher

from config import BOT_TOKEN, ADMIN_IDS, GIFT_BUDGET
from database import db
from middlewares.access import AccessMiddleware
from handlers import user_router, admin_router
from services.notifications import start_reminder_scheduler

async def main():
    if not BOT_TOKEN:
        print("=" * 50)
        print("[ERROR] ТОКЕН БОТА НЕ НАЙДЕН!")
        print("=" * 50)
        print("Установите переменную окружения `BOT_TOKEN` или добавьте её в файл `.env`.")
        print("Получить токен: @BotFather → /newbot")
        sys.exit(1)

    try:
        bot = Bot(token=BOT_TOKEN)
    except Exception as e:
        logging.error("Ошибка инициализации бота: %s", e)
        sys.exit(1)

    dp = Dispatcher()

    # Регистрируем мидлварь контроля доступа
    dp.update.middleware(AccessMiddleware(db))

    # Подключаем роутеры обработчиков
    dp.include_router(user_router)
    dp.include_router(admin_router)

    from aiogram.types import BotCommand, BotCommandScopeDefault

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Главное меню / Регистрация"),
            BotCommand(command="help", description="Справка и правила игры"),
            BotCommand(command="admin", description="Админ-панель"),
        ], scope=BotCommandScopeDefault())
    except Exception as e:
        logging.warning("Не удалось зарегистрировать команды бота: %s", e)

    total_participants = await db.get_total_participants()
    allowed_users = await db.get_allowed_users()
    deadline = await db.get_registration_deadline()
    bot_info = await bot.get_me()

    print("=" * 50)
    print("Бот Тайный Санта запущен!")
    print(f"Бот: @{bot_info.username}")
    print(f"Участников: {total_participants}")
    print(f"Бюджет подарка: {GIFT_BUDGET} рублей")
    print(f"Доступно для {len(allowed_users)} пользователей")
    print(f"Админы: {ADMIN_IDS}")
    print(f"Регистрация открыта до: {deadline.strftime('%d.%m.%Y %H:%M')}")
    print("=" * 50)

    # Запускаем фоновый планировщик напоминаний
    scheduler_task = asyncio.create_task(start_reminder_scheduler(bot, db))

    try:
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await bot.session.close()
        logging.info("Бот успешно остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот выключен.")
