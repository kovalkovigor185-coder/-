from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.keyboards import MENU, WELCOME, inline

router = Router()


@router.message(CommandStart())
async def start(m: Message, state: FSMContext, service):
    await state.clear()
    p = await service.profile(m.from_user.id)
    await m.answer(
        "Добро пожаловать! Здесь ты можешь находить людей, которые подходят тебе по интересам, "
        "характеру и целям знакомства.\n\nСоздай анкету, узнай совместимость и находи взаимные симпатии.",
        reply_markup=MENU if p else WELCOME,
    )
    if await service.draft(m.from_user.id):
        await m.answer("Есть сохранённый черновик.", reply_markup=inline([("Продолжить", "register")]))


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext, service):
    await state.clear()
    await service.cancel_draft(m.from_user.id)
    await m.answer("Отменено.", reply_markup=MENU)


async def show_rules(message):
    path = Path(__file__).resolve().parents[2] / "docs" / "RULES.md"
    await message.answer(path.read_text(encoding="utf-8"))


@router.message(Command("rules"))
async def rules_command(m: Message):
    await show_rules(m)


@router.callback_query(F.data.in_({"rules", "help", "menu"}))
async def info(c: CallbackQuery):
    await c.answer()
    if c.data == "rules":
        await show_rules(c.message)
    elif c.data == "help":
        await c.message.answer(
            "Создайте анкету 18+, просматривайте людей и ставьте лайки. Взаимный лайк создаёт "
            "совпадение. Контакты доступны только после отдельного согласия обоих. "
            "Совместимость — условная оценка общих интересов и предпочтений."
        )
    else:
        await c.message.answer("Главное меню", reply_markup=MENU)
