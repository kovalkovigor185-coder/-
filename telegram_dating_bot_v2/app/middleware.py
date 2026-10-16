import asyncio
import logging
import time
from collections import OrderedDict

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from app.models import User


class GuardMiddleware(BaseMiddleware):
    def __init__(self):
        self.locks = {}
        self.last = OrderedDict()
        self.seen = OrderedDict()

    async def __call__(self, handler, event, data):
        if not isinstance(event, (Message, CallbackQuery)) or not event.from_user:
            return
        message = event.message if isinstance(event, CallbackQuery) else event
        if not message or message.chat.type != "private":
            return
        uid = event.from_user.id
        async with self.locks.setdefault(uid, asyncio.Lock()):
            if isinstance(event, CallbackQuery):
                if event.id in self.seen:
                    await event.answer("Уже обработано")
                    return
                self.seen[event.id] = True
                if len(self.seen) > 10000:
                    self.seen.popitem(last=False)
            now = time.monotonic()
            if now - self.last.get(uid, 0) < 0.5:
                if isinstance(event, CallbackQuery):
                    await event.answer("Подождите секунду")
                return
            self.last[uid] = now
            if len(self.last) > 10000:
                expired, _ = self.last.popitem(last=False)
                if expired != uid and not self.locks[expired].locked():
                    self.locks.pop(expired, None)
            service = data["service"]
            try:
                await service.ensure_user(uid, event.from_user.username)
                async with service.db.sessions() as s:
                    u = await s.get(User, uid)
                    banned = u.banned
                privacy_action = (
                    isinstance(event, Message)
                    and event.text in {"/start", "/rules", "/cancel", "⚙️ Настройки"}
                    or isinstance(event, CallbackQuery)
                    and event.data in {"delete_ask", "delete_confirm", "rules", "menu", "ai_off"}
                )
                if banned and not privacy_action:
                    if isinstance(event, CallbackQuery):
                        await event.answer("Доступ ограничен")
                    else:
                        await message.answer("Доступ ограничен. Обратитесь к оператору сервиса.")
                    return
                return await handler(event, data)
            except ValueError:
                await message.answer("Действие недоступно или данные некорректны. Откройте раздел заново.")
            except TelegramAPIError:
                logging.getLogger(__name__).warning("Ошибка Telegram API, операция могла сохраниться")
            except Exception:
                logging.getLogger(__name__).error("Внутренняя ошибка обработки события")
                await message.answer("Не удалось выполнить действие. Попробуйте позже или отправьте /start.")
