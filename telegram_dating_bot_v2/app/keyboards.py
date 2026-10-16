from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def inline(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in rows
        ]
    )


MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Смотреть анкеты"), KeyboardButton(text="❤️ Симпатии")],
        [KeyboardButton(text="💬 Совпадения"), KeyboardButton(text="👤 Моя анкета")],
        [KeyboardButton(text="⚙️ Настройки")],
    ],
    resize_keyboard=True,
)

WELCOME = inline(
    [("Создать анкету", "register")],
    [("Как это работает", "help")],
    [("Правила и конфиденциальность", "rules")],
)
