from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("admin"))
async def admin(m: Message, service, settings):
    if m.from_user.id not in settings.admins:
        await m.answer("Нет доступа")
        return
    args = (m.text or "").split()
    if len(args) == 1:
        await m.answer(
            "/admin stats | reports | ban ID | unban ID | hide ID | view ID | resolve НОМЕР_ЖАЛОБЫ"
        )
        return
    action = args[1]
    target = int(args[2]) if len(args) > 2 else 0
    if action == "view":
        from app.handlers.registration import text_profile

        p = await service.profile(target)
        if p:
            await m.answer(text_profile(p))
            for photo in p["photos"]:
                await m.answer_photo(photo)
        else:
            await m.answer("Анкета не найдена")
        return
    result = await service.admin(m.from_user.id, settings.admins, action, target)
    await m.answer(str(result)[:4000])
