from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🥗 Добавить еду"), KeyboardButton(text="📓 Мой дневник")],
            [KeyboardButton(text="📊 Рассчитать % жира"), KeyboardButton(text="📈 Статистика за неделю")],
            [KeyboardButton(text="💪 Планы питания"), KeyboardButton(text="👤 Мой профиль")]
        ],
        resize_keyboard=True
    )

def gender_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужской"), KeyboardButton(text="Женский")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def plans_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌱 Базовый план (7 дней) - 50⭐", callback_data="buy_basic")],
            [InlineKeyboardButton(text="💪 PRO план (30 дней) - 100⭐", callback_data="buy_pro")],
            [InlineKeyboardButton(text="👑 Премиум план (90 дней) - 250⭐", callback_data="buy_premium")]
        ]
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )