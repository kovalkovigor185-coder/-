import asyncio

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select

from app.models import Match


async def deliver(bot, dating):
    async with dating.db.sessions() as s:
        keys = [(m.a, m.b) for m in await s.scalars(select(Match).where(Match.active.is_(True)))]
    for a, b in keys:
        for uid, field in ((a, "notified_a"), (b, "notified_b")):
            async with dating.db.transaction() as s:
                m = await s.get(Match, (a, b))
                if not m or not m.active or getattr(m, field) or not await dating.accessible(s, a, b):
                    continue
                try:
                    await bot.send_message(uid, "У вас взаимная симпатия! Откройте «💬 Совпадения».")
                except TelegramAPIError:
                    continue
                setattr(m, field, True)


async def notification_loop(bot, dating):
    while True:
        try:
            await deliver(bot, dating)
        except Exception:
            # Never log exception text: network errors may include credentials or personal data.
            import logging

            logging.getLogger(__name__).warning("Ошибка доставки уведомлений")
        await asyncio.sleep(30)
