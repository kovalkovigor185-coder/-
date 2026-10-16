from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.handlers.registration import text_profile
from app.keyboards import inline

router = Router()


@router.message(F.text == "❤️ Симпатии")
async def likes(m: Message, service):
    incoming, names = await service.likes(m.from_user.id)
    await m.answer(
        f"Получено симпатий: {incoming}\nВам понравились: " + (", ".join(names[:50]) or "пока никого")
    )


@router.message(F.text == "💬 Совпадения")
async def matches(m: Message, service):
    profiles = await service.matches(m.from_user.id)
    if not profiles:
        await m.answer("Совпадений пока нет.")
    for p in profiles[:30]:
        await m.answer(p["name"], reply_markup=inline([("Посмотреть", f"match:{p['user_id']}")]))


@router.callback_query(F.data.regexp(r"^(match|contact|revoke|unmatch):"))
async def action(c: CallbackQuery, service):
    action, target = c.data.split(":")
    target = int(target)
    uid = c.from_user.id
    await c.answer()
    profiles = await service.matches(uid)
    p = next((p for p in profiles if p["user_id"] == target), None)
    if not p:
        await c.message.answer("Совпадение недоступно.")
        return
    if action == "match":
        await c.message.answer_photo(
            p["photos"][0],
            caption=text_profile(p),
            reply_markup=inline(
                [("Согласен раскрыть мой @username", f"contact:{target}")],
                [("Отозвать согласие", f"revoke:{target}")],
                [("Все фото", f"photos:{target}")],
                [("Пожаловаться", f"report:{target}"), ("Заблокировать", f"block:{target}")],
                [("Удалить совпадение", f"unmatch:{target}")],
            ),
        )
    elif action == "unmatch":
        await service.remove_match(uid, target)
        await c.message.answer("Совпадение удалено.")
    else:
        from aiogram.exceptions import TelegramAPIError

        contacts = await service.contacts(uid, target, action == "contact")
        if contacts:
            own, other = contacts
            if own and other:
                from app.models import ContactConsent, Match, User

                async with service.db.transaction() as session:
                    match = await session.get(Match, tuple(sorted((uid, target))))
                    ca = await session.get(ContactConsent, (uid, target))
                    cb = await session.get(ContactConsent, (target, uid))
                    if not (
                        match
                        and match.active
                        and ca
                        and ca.granted
                        and cb
                        and cb.granted
                        and await service.accessible(session, uid, target)
                    ):
                        await c.message.answer("Согласие изменилось. Откройте совпадение заново.")
                        return
                    own = (await session.get(User, uid)).username
                    other = (await session.get(User, target)).username
                    if not own or not other:
                        await c.message.answer("Обоим участникам нужен публичный @username.")
                        return
                    await c.message.answer("Оба согласны на обмен. Контакт: @" + other)
                    try:
                        await c.bot.send_message(target, "Оба согласны на обмен. Контакт: @" + own)
                    except TelegramAPIError:
                        await c.message.answer(
                            "Уведомление второму участнику не доставлено. Он может открыть совпадение повторно."
                        )
            else:
                await c.message.answer(
                    "Для обмена обоим нужен публичный @username в Telegram. "
                    "Укажите его в настройках Telegram, затем отправьте /start."
                )
        else:
            await c.message.answer(
                "Согласие сохранено. Ждём второго участника."
                if action == "contact"
                else "Согласие отозвано. Уже раскрытый контакт отозвать невозможно."
            )
