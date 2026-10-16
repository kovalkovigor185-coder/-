import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.bot_factory import create_bot
from app.config import Settings
from app.main import build_dispatcher


class TelegramMock(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, (AnswerCallbackQuery, EditMessageReplyMarkup)):
            return True
        return Message(
            message_id=len(self.sent),
            date=datetime.now(timezone.utc),
            chat=Chat(id=int(method.chat_id), type="private"),
            text=getattr(method, "text", None),
            caption=getattr(method, "caption", None),
            reply_markup=getattr(method, "reply_markup", None),
        )

    async def stream_content(self, *args, **kwargs):
        yield b""


async def test_dispatcher_registration_flow(service):
    session = TelegramMock()
    bot = Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    dp = build_dispatcher(service, Settings(_env_file=None))
    user = User(id=42, is_bot=False, first_name="Анна", username="anna")
    counter = 0

    async def send(text=None, callback=None, photo=False):
        nonlocal counter
        counter += 1
        m = Message(
            message_id=counter,
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=user,
            text=text,
            photo=[{"file_id": "photo", "file_unique_id": "p", "width": 100, "height": 100, "file_size": 200}]
            if photo
            else None,
        )
        if callback:
            event = Update(
                update_id=counter,
                callback_query=CallbackQuery(
                    id=str(counter), from_user=user, chat_instance="x", message=m, data=callback
                ),
            )
        else:
            event = Update(update_id=counter, message=m)
        # Preserve real middleware behavior; exceed the documented per-user throttle.
        await asyncio.sleep(0.51)
        await dp.feed_update(bot, event)

    await send("/start")
    await send(callback="register")
    assert any("18" in (getattr(x, "text", "") or "") for x in session.sent)
    await send(callback="adult")
    for value in ["Анна", "25", "женщина", "любой", "Омск", "дружба", "кино", "Привет", "18-40", "любой"]:
        await send(value)
    await send(photo=True)
    await send(callback="regdone|10")
    await send(callback="regpublish")
    assert (await service.profile(42))["published"]
    assert await service.draft(42) is None
    await send("👤 Моя анкета")
    assert any("Анна" in (getattr(x, "caption", "") or "") for x in session.sent)
    await service.admin(99, {99}, "ban", 42)
    await send("⚙️ Настройки")
    await send(callback="delete_ask")
    await send(callback="delete_confirm")
    assert await service.profile(42) is None
    await bot.session.close()
    await dp.storage.close()


async def test_proxy_session():
    cfg = Settings(
        _env_file=None,
        bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        proxy_url="socks5://localhost:1080",
    )
    bot = create_bot(cfg)
    assert bot.session._proxy == "socks5://localhost:1080"
    await bot.session.close()
