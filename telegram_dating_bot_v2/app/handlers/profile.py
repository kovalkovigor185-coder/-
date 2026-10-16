from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.registration import begin, text_profile
from app.keyboards import inline

router = Router()


@router.message(F.text == "👤 Моя анкета")
async def own(m: Message, service):
    p = await service.profile(m.from_user.id)
    if not p:
        await m.answer("Создайте анкету через /start")
        return
    await m.answer_photo(
        p["photos"][0],
        caption=text_profile(p) + ("\nОпубликована" if p["published"] else "\nСкрыта"),
        reply_markup=inline(
            [("Редактировать все поля", "edit")],
            [("Управлять фото", "myphotos")],
            [("Скрыть" if p["published"] else "Вернуть в поиск", "visibility")],
        ),
    )


@router.callback_query(F.data.in_({"edit", "visibility", "myphotos"}) | F.data.startswith("photoedit:"))
async def edit(c: CallbackQuery, state: FSMContext, service):
    await c.answer()
    uid = c.from_user.id
    p = await service.profile(uid)
    if not p:
        return
    if c.data == "edit":
        await begin(c.message, uid, state, service, edit=True)
    elif c.data == "visibility":
        await service.visibility(uid, not p["published"])
        await c.message.answer("Видимость изменена.")
    elif c.data == "myphotos":
        import hashlib

        fingerprint = hashlib.sha256("|".join(p["photos"]).encode()).hexdigest()[:10]
        for i, photo in enumerate(p["photos"]):
            await c.message.answer_photo(
                photo,
                reply_markup=inline(
                    [
                        ("Сделать главным", f"photoedit:main:{i}:{fingerprint}"),
                        ("Удалить", f"photoedit:delete:{i}:{fingerprint}"),
                    ]
                ),
            )
        await c.message.answer(
            "Для добавления фото откройте редактирование анкеты. Остальные поля можно сохранить прежними."
        )
    else:
        _, action, position, expected = c.data.split(":")
        await service.photo_action(uid, int(position), action == "delete", expected)
        await c.message.edit_reply_markup(reply_markup=None)
        await c.message.answer("Фото обновлены. Откройте раздел заново перед следующим изменением.")
