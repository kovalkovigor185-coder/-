from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import Settings


def create_bot(settings: Settings) -> Bot:
    return Bot(
        settings.bot_token.get_secret_value(),
        session=AiohttpSession(
            proxy=settings.proxy_url.get_secret_value() or None,
            timeout=20,
        ),
    )
