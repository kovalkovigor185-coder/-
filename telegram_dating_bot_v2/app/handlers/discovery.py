from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.handlers.registration import text_profile
from app.keyboards import inline
from app.services.compatibility import calculate

router = Router()
REASONS = [
    "Спам",
    "Фейковая анкета",
    "Оскорбления",
    "Неподходящий контент",
    "Подозрение на возраст до 18",
    "Другая причина",
]


async def show(message, uid, service, settings):
    b = await service.candidate(uid)
    if not b:
        await message.answer(
            "Подходящих анкет пока нет. Проверьте публикацию своей анкеты и настройки поиска."
        )
        return
    a = await service.profile(uid)
    score = calculate(a, b, settings.compatibility_weights)
    t = b["user_id"]
    await message.answer_photo(
        b["photos"][0],
        caption=text_profile(b) + f"\n\nСовместимость: {score.percent}%.",
        reply_markup=inline(
            [("❤️ Нравится", f"like:{t}"), ("Пропустить", f"skip:{t}")],
            [("Почему мы подходим?", f"why:{t}")],
            [("Фото", f"photos:{t}")],
            [("Пожаловаться", f"report:{t}"), ("Заблокировать", f"block:{t}")],
            [("Назад в меню", "menu")],
        ),
    )


@router.message(F.text == "🔎 Смотреть анкеты")
async def discover(m: Message, service, settings):
    await show(m, m.from_user.id, service, settings)


@router.callback_query(F.data.regexp(r"^(like|skip|why|photos|report|reason|block):"))
async def action(c: CallbackQuery, service, settings, ai_service):
    parts = c.data.split(":")
    action, target = parts[0], int(parts[1])
    uid = c.from_user.id
    await c.answer()
    if action in {"like", "skip"}:
        await service.react(uid, target, action == "like")
        await c.message.edit_reply_markup(reply_markup=None)
        await show(c.message, uid, service, settings)
        return
    # Existing matches remain viewable if preferences change; visibility still checked for discovery.
    matches = await service.matches(uid)
    b = next((p for p in matches if p["user_id"] == target), None)
    b = b or await service.candidate(uid, target, rated=True)
    if not b:
        await c.message.answer("Анкета недоступна")
        return
    if action == "why":
        a = await service.profile(uid)
        result = calculate(a, b, settings.compatibility_weights)
        await c.message.answer(await ai_service.explain(a, b, result))
    elif action == "photos":
        for photo in b["photos"]:
            await c.message.answer_photo(photo)
    elif action == "report":
        await c.message.answer(
            "Причина жалобы:",
            reply_markup=inline(*[[(reason, f"reason:{target}:{i}")] for i, reason in enumerate(REASONS)]),
        )
    elif action == "reason":
        index = int(parts[2])
        if 0 <= index < len(REASONS):
            await service.report(uid, target, REASONS[index])
            await c.message.answer("Жалоба передана администраторам.")
    elif action == "block":
        await service.block(uid, target)
        await c.message.answer("Пользователь заблокирован.")
