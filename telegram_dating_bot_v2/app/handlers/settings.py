from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.keyboards import WELCOME, inline

router = Router()


class Deletion(StatesGroup):
    confirm = State()


@router.message(F.text == "⚙️ Настройки")
async def settings(m: Message, service, settings):
    consent = await service.has_consent(m.from_user.id, "external_ai_v1")
    await m.answer(
        "AI: "
        + ("согласие дано" if consent else "выключен")
        + "\nПри согласии обоих участников внешнему провайдеру передаются описания, интересы и цели. "
        "Текст может содержать введённые вами личные сведения. Фото, ID и имя не передаются. "
        "AI необязателен. Отзыв не удаляет ранее отправленные данные у провайдера. "
        "Оператор должен указать провайдера в политике до включения AI.",
        reply_markup=inline(
            [
                (
                    "Отозвать согласие" if consent else "Разрешить передачу текста AI",
                    "ai_off" if consent else "ai_on",
                )
            ],
            [("Настроить поиск", "edit")],
            [("Удалить мои данные", "delete_ask")],
        ),
    )


@router.callback_query(F.data.in_({"ai_on", "ai_off", "delete_ask", "delete_confirm"}))
async def controls(c: CallbackQuery, state: FSMContext, service):
    await c.answer()
    if c.data.startswith("ai_"):
        await service.consent(c.from_user.id, "external_ai_v1", c.data == "ai_on")
        await c.message.answer("Настройка согласия сохранена.")
    elif c.data == "delete_ask":
        await state.set_state(Deletion.confirm)
        await c.message.answer(
            "Удалить анкету, фото, лайки, совпадения и остальные данные из базы? "
            "Действие необратимо. Копии сообщений в Telegram не удаляются.",
            reply_markup=inline([("Удалить навсегда", "delete_confirm")], [("Отмена", "menu")]),
        )
    else:
        if await state.get_state() != Deletion.confirm.state:
            await c.message.answer("Откройте удаление заново через настройки.")
            return
        await service.delete_user(c.from_user.id)
        await state.clear()
        await c.message.answer("Данные удалены из базы бота.", reply_markup=WELCOME)
