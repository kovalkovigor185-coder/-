from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError

from app.keyboards import MENU, inline
from app.validation import GENDERS, GOALS, ProfileInput

router = Router()


class Registration(StatesGroup):
    filling = State()
    preview = State()


FIELDS = [
    "name",
    "age",
    "gender",
    "search_gender",
    "city",
    "goal",
    "interests",
    "bio",
    "ages",
    "search_city",
    "photos",
]
PROMPTS = [
    "Как вас называть? До 50 символов.",
    "Укажите возраст: от 18 до 100 лет.",
    "Укажите пол или пропустите.",
    "Кого показывать в поиске?",
    "Ваш город (до 80 символов)?",
    "Какая у вас цель знакомства?",
    "Интересы через запятую (до 15). Можно выбрать категорию кнопкой и дополнить текстом.",
    "Расскажите о себе (до 500 символов).",
    "Возраст партнёра: например 18-35.",
    "Город поиска? Введите город или «любой». Поиск по расстоянию в MVP не используется.",
    "Отправьте 1–5 фотографий как фото (JPEG, до 10 МБ каждая), затем нажмите «Готово».",
]
OPTIONAL = {2: "не указан", 3: "любой", 6: [], 7: "", 8: "18-100", 9: "любой"}


def text_profile(p: dict) -> str:
    return (
        f"{p['name']}, {p['age']} лет\n{p['city']}\n\nО себе: {p['bio'] or 'не указано'}"
        f"\nИнтересы: {', '.join(p['interests']) or 'не указаны'}\nЦель: {p['goal']}"
    )[:900]


async def show_step(message: Message, service, uid: int):
    step, data = await service.draft(uid)
    rows = []
    choices = {
        2: sorted(GENDERS),
        3: ["мужчина", "женщина", "любой"],
        5: sorted(GOALS),
        6: ["спорт", "кино", "музыка", "путешествия", "игры", "книги"],
    }.get(step, [])
    for choice in choices:
        rows.append([(choice, f"regvalue:{choice}")])
    if step in OPTIONAL:
        rows.append([("Пропустить", "regskip")])
    if step == 6:
        rows.append([("Готово", "reginterests")])
    if step == 10:
        rows.append([("Готово", "regdone")])
    if step > 0:
        rows.append([("Назад", "regback")])
    rows.append([("Отмена", "regcancel")])
    extra = f"\nЗагружено: {len(data.get('photos', []))}" if step == 10 else ""
    if step == 6:
        extra = "\nВыбрано: " + ", ".join(data.get("interests", []))
    rows = [[(label, f"{action}|{step}") for label, action in row] for row in rows]
    await message.answer(PROMPTS[step] + extra, reply_markup=inline(*rows))


async def begin(message, uid, state, service, edit=False):
    if not await service.has_consent(uid, "adult_rules_v1"):
        await message.answer(
            "Подтвердите: вам исполнилось 18 лет и вы принимаете правила и политику (команда /rules).",
            reply_markup=inline([("Мне 18+, принимаю", "adult")]),
        )
        return
    draft = await service.draft(uid)
    if edit:
        p = await service.profile(uid)
        data = ProfileInput(**p).model_dump() if p else {}
        data["ages"] = f"{data.get('min_age', 18)}-{data.get('max_age', 100)}"
        await service.draft(uid, 0, data)
    elif not draft:
        await service.draft(uid, 0, {})
    elif draft[0] == len(FIELDS):
        await preview(message, uid, state, service)
        return
    await state.set_state(Registration.filling)
    await show_step(message, service, uid)


async def preview(message, uid, state, service):
    _, data = await service.draft(uid)
    p = ProfileInput(**data)
    await state.set_state(Registration.preview)
    await message.answer_photo(
        p.photos[0],
        caption=text_profile(p.model_dump()),
        reply_markup=inline(
            [("Опубликовать", "regpublish")],
            [("Редактировать", "regrestart"), ("Добавить фото", "regphotos")],
            [("Отмена", "regcancel")],
        ),
    )


async def accept(message, uid, state, service, value):
    draft = await service.draft(uid)
    if not draft or draft[0] >= len(FIELDS):
        return
    step, data = draft
    key = FIELDS[step]
    data = dict(data)
    try:
        if key == "photos":
            photos = list(data.get("photos", []))
            if value == "Готово":
                if not photos:
                    raise ValueError("Добавьте хотя бы одно фото")
            elif isinstance(value, tuple):
                file_id, size = value
                if size > 10 * 1024 * 1024 or len(photos) >= 5:
                    raise ValueError("Максимум 5 фото, до 10 МБ каждое")
                photos.append(file_id)
                data[key] = photos
                await service.draft(uid, step, data)
                await show_step(message, service, uid)
                return
            else:
                raise ValueError("Отправьте изображение как фото")
        elif key == "age":
            if not 18 <= int(value) <= 100:
                raise ValueError("Только пользователи от 18 до 100 лет")
            data[key] = int(value)
        elif key == "ages":
            low, high = map(int, str(value).split("-"))
            if not 18 <= low <= high <= 100:
                raise ValueError("Диапазон от 18 до 100")
            data.update(min_age=low, max_age=high)
        elif key == "interests":
            interests = value if isinstance(value, list) else str(value).casefold().split(",")
            interests = sorted({x.strip() for x in interests if x.strip()})
            if len(interests) > 15 or any(len(x) > 40 for x in interests):
                raise ValueError("До 15 интересов, каждый до 40 символов")
            data[key] = interests
        else:
            value = str(value).strip()
            limits = {"name": 50, "city": 80, "search_city": 80, "bio": 500}
            if key in limits and (len(value) > limits[key] or not value and key != "bio"):
                raise ValueError(f"Проверьте длину: до {limits[key]} символов")
            if key == "gender" and value not in GENDERS:
                raise ValueError("Используйте кнопки выбора пола")
            if key == "search_gender" and value not in GENDERS | {"любой"}:
                raise ValueError("Используйте кнопки выбора")
            if key == "goal" and value not in GOALS:
                raise ValueError("Используйте кнопки выбора цели")
            data[key] = value
        next_step = step + 1
        if next_step == len(FIELDS):
            ProfileInput(**data)
        await service.draft(uid, next_step, data)
        if next_step == len(FIELDS):
            await preview(message, uid, state, service)
        else:
            await show_step(message, service, uid)
    except (ValueError, TypeError, ValidationError):
        await message.answer("Некорректное значение. " + PROMPTS[step])


@router.callback_query(F.data == "register")
async def register(c: CallbackQuery, state: FSMContext, service):
    await c.answer()
    await begin(c.message, c.from_user.id, state, service)


@router.callback_query(F.data == "adult")
async def adult(c: CallbackQuery, state: FSMContext, service):
    await service.consent(c.from_user.id, "adult_rules_v1", True)
    await c.answer()
    await begin(c.message, c.from_user.id, state, service)


@router.callback_query(F.data.startswith("reg"))
async def controls(c: CallbackQuery, state: FSMContext, service):
    await c.answer()
    uid = c.from_user.id
    draft = await service.draft(uid)
    if not draft:
        await c.message.answer("Черновик не найден. Начните через /start")
        return
    step, data = draft
    action, _, expected = c.data.partition("|")
    if expected and int(expected) != step:
        await c.message.answer("Этот шаг уже завершён. Используйте последние кнопки.")
        return
    if action == "regcancel":
        await service.cancel_draft(uid)
        await state.clear()
        await c.message.answer("Заполнение отменено.", reply_markup=MENU)
    elif action in {"regback", "regrestart", "regphotos"}:
        step = max(0, step - 1) if action == "regback" else (10 if action == "regphotos" else 0)
        await service.draft(uid, step, data)
        await state.set_state(Registration.filling)
        await show_step(c.message, service, uid)
    elif action == "regpublish" and step == len(FIELDS):
        await service.save_profile(uid, ProfileInput(**data))
        await state.clear()
        await c.message.answer("Анкета опубликована.", reply_markup=MENU)
    elif action == "regskip" and step in OPTIONAL:
        await accept(c.message, uid, state, service, OPTIONAL[step])
    elif action == "regdone" and step == 10:
        await accept(c.message, uid, state, service, "Готово")
    elif action == "reginterests" and step == 6:
        await accept(c.message, uid, state, service, data.get("interests", []))
    elif action.startswith("regvalue:") and step == 6:
        interest = action.split(":", 1)[1]
        selected = list(data.get("interests", []))
        if interest in selected:
            selected.remove(interest)
        elif len(selected) < 15:
            selected.append(interest)
        await service.draft(uid, step, data | {"interests": selected})
        await show_step(c.message, service, uid)
    elif action.startswith("regvalue:") and step in {2, 3, 5}:
        await accept(c.message, uid, state, service, action.split(":", 1)[1])


@router.message(Registration.filling)
async def fill(message: Message, state: FSMContext, service):
    value = (
        (message.photo[-1].file_id, message.photo[-1].file_size or 0) if message.photo else message.text or ""
    )
    await accept(message, message.from_user.id, state, service, value)


@router.message(Registration.preview)
async def preview_message(message: Message):
    await message.answer("Опубликуйте анкету или нажмите «Редактировать».")
