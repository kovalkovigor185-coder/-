import asyncio
import logging
from contextlib import suppress

from aiogram import Dispatcher
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.exc import SQLAlchemyError

from app.bot_factory import create_bot
from app.config import Settings
from app.database import Database
from app.handlers import admin, common, discovery, matches, profile, registration
from app.handlers import settings as settings_handlers
from app.middleware import GuardMiddleware
from app.services.ai_service import AIService
from app.services.dating import DatingService
from app.services.notifications import notification_loop


def build_dispatcher(service, settings) -> Dispatcher:
    dp = Dispatcher(service=service, settings=settings, ai_service=AIService(settings, service))
    guard = GuardMiddleware()
    dp.message.outer_middleware(guard)
    dp.callback_query.outer_middleware(guard)
    # Commands precede FSM; registration catches text only while filling.
    for router in (
        common.router,
        admin.router,
        registration.router,
        discovery.router,
        matches.router,
        profile.router,
        settings_handlers.router,
    ):
        dp.include_router(router)
    return dp


async def main():
    try:
        settings = Settings()
    except ValueError:
        print("Ошибка конфигурации .env. Проверьте значения без публикации секретов.")
        return
    if not settings.bot_token.get_secret_value():
        print("Заполните BOT_TOKEN в .env; затем выполните python scripts/check_connection.py")
        return
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    # Framework polling logs may include usernames; use only our fixed diagnostic messages.
    logging.getLogger("aiogram").setLevel(logging.CRITICAL)
    db = Database(settings.database_url)
    bot = None
    task = None
    try:
        bot = create_bot(settings)
        await bot.get_me()
        service = DatingService(db)
        dp = build_dispatcher(service, settings)
        task = asyncio.create_task(notification_loop(bot, service))
        await dp.start_polling(bot, close_bot_session=False)
    except (TelegramAPIError, OSError, ValueError, SQLAlchemyError):
        print("Ошибка запуска. Проверьте миграции, BOT_TOKEN и PROXY_URL; выполните скрипт проверки связи.")
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if bot:
            await bot.session.close()
        await db.engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
