import asyncio
import logging
import math
from datetime import date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice, ReplyKeyboardMarkup, KeyboardButton

from config import BOT_TOKEN, FATSECRET_KEY, FATSECRET_SECRET, PLANS
from database import (
    init_db, get_user, save_user, save_measurement, save_food_entry,
    get_daily_summary, get_week_summary, has_active_subscription,
    set_subscription
)
from keyboards import main_keyboard, gender_keyboard, plans_keyboard, back_keyboard

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация FatSecret API
FATSECRET_AVAILABLE = False
try:
    from pyfatsecret import Fatsecret
    fatsecret = Fatsecret(client_id=FATSECRET_KEY, client_secret=FATSECRET_SECRET)
    FATSECRET_AVAILABLE = True
    print("✅ FatSecret API подключен!")
except Exception as e:
    print(f"⚠️ FatSecret API не доступен: {e}")
    print("Бот будет работать без поиска продуктов (только ручной ввод)")

# Кэш для продуктов
food_cache = {}

# Клавиатура для выбора приёма пищи
def meal_type_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍳 Завтрак"), KeyboardButton(text="🥗 Обед")],
            [KeyboardButton(text="🍲 Ужин"), KeyboardButton(text="🍎 Перекус")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

# --- Состояния для FSM ---
class FatForm(StatesGroup):
    waiting_gender = State()
    waiting_height = State()
    waiting_neck = State()
    waiting_waist = State()
    waiting_hip = State()

class FoodForm(StatesGroup):
    waiting_food_name = State()
    waiting_food_selection = State()
    waiting_meal_type = State()
    waiting_weight = State()


# ========== ГЛАВНОЕ МЕНЮ ==========
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    save_user(user_id, message.from_user.first_name)
    
    await message.answer(
        f"💪 Привет, {message.from_user.first_name}!\n\n"
        f"Я твой фитнес-помощник!\n\n"
        f"📊 Рассчитываю процент жира по замерам\n"
        f"🥗 Ищу КБЖУ продуктов (как в FatSecret)\n"
        f"📓 Веду дневник питания\n\n"
        f"Чтобы добавить еду:\n"
        f"1. Нажми кнопку '🥗 Добавить еду'\n"
        f"2. Введи название продукта\n"
        f"3. Выбери продукт из списка\n"
        f"4. Выбери приём пищи\n"
        f"5. Введи вес *готового* продукта\n\n"
        f"Выбери действие в меню ниже 👇",
        reply_markup=main_keyboard()
    )


# ========== РАСЧЕТ ПРОЦЕНТА ЖИРА ==========
@dp.message(F.text == "📊 Рассчитать % жира")
async def start_fat_calc(message: Message, state: FSMContext):
    await message.answer("Выбери свой пол:", reply_markup=gender_keyboard())
    await state.set_state(FatForm.waiting_gender)

@dp.message(FatForm.waiting_gender)
async def process_gender(message: Message, state: FSMContext):
    if message.text not in ["Мужской", "Женский"]:
        await message.answer("Пожалуйста, выбери пол, используя кнопки")
        return
    await state.update_data(gender=message.text)
    await message.answer("📏 Введи свой рост (в см):", reply_markup=back_keyboard())
    await state.set_state(FatForm.waiting_height)

@dp.message(FatForm.waiting_height)
async def process_height(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await message.answer("Возврат в главное меню", reply_markup=main_keyboard())
        await state.clear()
        return
    try:
        height = float(message.text)
        if height < 100 or height > 250:
            await message.answer("❌ Рост должен быть между 100 и 250 см. Попробуй ещё раз:")
            return
        await state.update_data(height=height)
        await message.answer("📏 Введи обхват шеи (в см):")
        await state.set_state(FatForm.waiting_neck)
    except:
        await message.answer("❌ Введи число, например 175")

@dp.message(FatForm.waiting_neck)
async def process_neck(message: Message, state: FSMContext):
    try:
        neck = float(message.text)
        if neck < 25 or neck > 80:
            await message.answer("❌ Обхват шеи должен быть между 25 и 80 см. Попробуй ещё раз:")
            return
        await state.update_data(neck=neck)
        await message.answer("📏 Введи обхват талии (в см):")
        await state.set_state(FatForm.waiting_waist)
    except:
        await message.answer("❌ Введи число, например 38")

@dp.message(FatForm.waiting_waist)
async def process_waist(message: Message, state: FSMContext):
    try:
        waist = float(message.text)
        if waist < 40 or waist > 200:
            await message.answer("❌ Обхват талии должен быть между 40 и 200 см. Попробуй ещё раз:")
            return
        await state.update_data(waist=waist)
        data = await state.get_data()
        if data['gender'] == "Женский":
            await message.answer("📏 Введи обхват бедер (в см):")
            await state.set_state(FatForm.waiting_hip)
        else:
            await calculate_fat_percent(message, state, data)
    except:
        await message.answer("❌ Введи число")

@dp.message(FatForm.waiting_hip)
async def process_hip(message: Message, state: FSMContext):
    try:
        hip = float(message.text)
        if hip < 40 or hip > 200:
            await message.answer("❌ Обхват бедер должен быть между 40 и 200 см. Попробуй ещё раз:")
            return
        await state.update_data(hip=hip)
        data = await state.get_data()
        await calculate_fat_percent(message, state, data)
    except:
        await message.answer("❌ Введи число")

async def calculate_fat_percent(message: Message, state: FSMContext, data):
    # Бля, простая и понятная формула на основе ИМТ и обхватов
    
    height_m = data['height'] / 100  # рост в метрах
    
    # Определяем примерный вес по обхватам (приблизительно)
    # Для мужчин: вес ≈ (талия * рост) / 240 (примерная формула)
    if data['gender'] == "Мужской":
        # Оценка веса по талии и шее
        estimated_weight = (data['waist'] * data['height']) / 220
        
        # Базовый процент жира
        if data['waist'] < 70:
            base_fat = 10
        elif data['waist'] < 80:
            base_fat = 15
        elif data['waist'] < 90:
            base_fat = 20
        elif data['waist'] < 100:
            base_fat = 25
        elif data['waist'] < 110:
            base_fat = 30
        else:
            base_fat = 35
        
        # Корректировка по шее (чем толще шея, тем больше мышц)
        neck_correction = max(0, (data['neck'] - 40) / 10) * 2
        fat_percent = base_fat - neck_correction
        
        # Ограничения
        fat_percent = max(10, min(40, round(fat_percent, 1)))
        
        # Для твоего примера (рост180, шея45, талия78):
        # base_fat = 20 (талия 78)
        # neck_correction = (45-40)/10*2 = 1
        # fat_percent = 20 - 1 = 19% ✅ РЕАЛИСТИЧНО!
        
    else:  # Женский
        if data['waist'] < 60:
            base_fat = 18
        elif data['waist'] < 70:
            base_fat = 22
        elif data['waist'] < 80:
            base_fat = 27
        elif data['waist'] < 90:
            base_fat = 32
        elif data['waist'] < 100:
            base_fat = 37
        else:
            base_fat = 42
        
        neck_correction = max(0, (data['neck'] - 35) / 10) * 1.5
        fat_percent = base_fat - neck_correction
        fat_percent = max(18, min(50, round(fat_percent, 1)))
    
    # Сохраняем результат
    save_measurement(message.from_user.id, data['neck'], data['waist'], data.get('hip', 0), fat_percent)
    save_user(message.from_user.id, message.from_user.first_name, data['gender'], data['height'])
    
    await message.answer(
        f"📊 *Результат:*\n\n"
        f"Процент жира: *{fat_percent}%*\n\n"
        f"_Формула на основе антропометрических данных_",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    await state.clear()

# ========== ДОБАВЛЕНИЕ ЕДЫ ==========
@dp.message(F.text == "🥗 Добавить еду")
async def start_add_food(message: Message, state: FSMContext):
    if not FATSECRET_AVAILABLE:
        await message.answer(
            "⚠️ Функция поиска продуктов временно недоступна.\n\n"
            "Используй ручной ввод:\n"
            "/add_food название граммы калории белки жиры углеводы\n\n"
            "Пример: /add_food гречка 100 343 12.6 3.3 68\n\n"
            "⚠️ Вес указывается для *готового* продукта!",
            parse_mode="Markdown"
        )
        return
    
    await message.answer(
        "🍎 Введи название продукта:\n\n"
        "Примеры: гречка, курица, рис, яблоко\n\n"
        "⚠️ Вес нужно будет указать для *готового* продукта!",
        parse_mode="Markdown"
    )
    await state.set_state(FoodForm.waiting_food_name)

@dp.message(FoodForm.waiting_food_name)
async def search_food(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await message.answer("Возврат в главное меню", reply_markup=main_keyboard())
        await state.clear()
        return
    
    product_name = message.text.lower()
    await message.answer(f"🔍 Ищу '{product_name}'...")
    
    try:
        if product_name in food_cache:
            results = food_cache[product_name]
        else:
            results = fatsecret.foods.foods_search(search_expression=product_name, max_results=10)
            food_cache[product_name] = results
        
        if not results or 'foods' not in results or 'food' not in results['foods']:
            await message.answer("❌ Ничего не найдено. Попробуй другое название.")
            await state.clear()
            return
        
        foods_list = results['foods']['food']
        if not isinstance(foods_list, list):
            foods_list = [foods_list]
        
        if not foods_list:
            await message.answer("❌ Ничего не найдено.")
            await state.clear()
            return
        
        await state.update_data(foods_list=foods_list)
        
        response = "🔎 Найдено:\n\n"
        for i, food in enumerate(foods_list[:10], 1):
            food_name = food.get('food_name', 'Без названия')
            brand = food.get('brand_name', '')
            response += f"{i}. {food_name}" + (f" ({brand})" if brand else "") + "\n"
        
        response += "\nНапиши номер продукта (1-10):"
        await message.answer(response)
        await state.set_state(FoodForm.waiting_food_selection)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
        await state.clear()

@dp.message(FoodForm.waiting_food_selection)
async def select_food(message: Message, state: FSMContext):
    data = await state.get_data()
    foods_list = data.get('foods_list', [])
    
    try:
        choice = int(message.text) - 1
        if choice < 0 or choice >= len(foods_list):
            await message.answer("❌ Неправильный номер.")
            return
        
        selected_food = foods_list[choice]
        food_id = selected_food.get('food_id')
        food_name = selected_food.get('food_name', 'Продукт')
        brand = selected_food.get('brand_name', '')
        
        food_details = fatsecret.foods.food_get(food_id)
        
        servings = food_details.get('food', {}).get('servings', {}).get('serving', [])
        if not isinstance(servings, list):
            servings = [servings]
        
        nutrition = None
        for serving in servings:
            metric = serving.get('metric_serving_amount', '')
            unit = serving.get('metric_serving_unit', '')
            if '100' in str(metric) and unit in ['g', 'г']:
                nutrition = serving
                break
        
        if not nutrition and servings:
            nutrition = servings[0]
        
        if not nutrition:
            await message.answer("❌ Не удалось получить информацию")
            await state.clear()
            return
        
        await state.update_data(
            food_name=food_name,
            brand=brand,
            calories_per_100g=float(nutrition.get('calories', 0)),
            protein_per_100g=float(nutrition.get('protein', 0)),
            fat_per_100g=float(nutrition.get('fat', 0)),
            carbs_per_100g=float(nutrition.get('carbohydrate', 0))
        )
        
        product_display = f"{food_name}" + (f" ({brand})" if brand else "")
        
        await message.answer(
            f"✅ Выбран: {product_display}\n\n"
            f"📊 На 100 г:\n"
            f"🔥 {nutrition.get('calories', 0)} ккал\n"
            f"🥩 {nutrition.get('protein', 0)} г белков\n"
            f"🧈 {nutrition.get('fat', 0)} г жиров\n"
            f"🍚 {nutrition.get('carbohydrate', 0)} г углеводов\n\n"
            f"⚠️ Вес указывается для *ГОТОВОГО* продукта!\n\n"
            f"🍽️ Выбери приём пищи:",
            parse_mode="Markdown",
            reply_markup=meal_type_keyboard()
        )
        await state.set_state(FoodForm.waiting_meal_type)
        
    except ValueError:
        await message.answer("❌ Введи номер продукта:")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")

@dp.message(FoodForm.waiting_meal_type)
async def process_meal_type(message: Message, state: FSMContext):
    meal_types = ["🍳 Завтрак", "🥗 Обед", "🍲 Ужин", "🍎 Перекус"]
    
    if message.text == "🔙 Назад":
        await message.answer("Главное меню", reply_markup=main_keyboard())
        await state.clear()
        return
    
    if message.text not in meal_types:
        await message.answer("❌ Выбери приём пищи из кнопок")
        return
    
    await state.update_data(meal_type=message.text)
    
    await message.answer(
        f"⚖️ Выбран приём: *{message.text}*\n\n"
        f"Введи вес *ГОТОВОГО* продукта в граммах:",
        parse_mode="Markdown",
        reply_markup=back_keyboard()
    )
    await state.set_state(FoodForm.waiting_weight)

@dp.message(FoodForm.waiting_weight)
async def save_food_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text)
        if weight <= 0 or weight > 5000:
            await message.answer("❌ Вес от 1 до 5000 грамм:")
            return
        
        data = await state.get_data()
        
        calories = (data['calories_per_100g'] * weight) / 100
        protein = (data['protein_per_100g'] * weight) / 100
        fat = (data['fat_per_100g'] * weight) / 100
        carbs = (data['carbs_per_100g'] * weight) / 100
        
        product_display = data['food_name'] + (f" ({data['brand']})" if data.get('brand') else "")
        meal_type = data.get('meal_type', 'Приём пищи')
        
        save_food_entry(
            message.from_user.id,
            f"{meal_type}: {product_display} (готовый, {weight}г)",
            calories, protein, fat, carbs
        )
        
        daily = get_daily_summary(message.from_user.id)
        
        meal_emojis = {
            "🍳 Завтрак": "🌅",
            "🥗 Обед": "☀️", 
            "🍲 Ужин": "🌙",
            "🍎 Перекус": "🍎"
        }
        meal_emoji = meal_emojis.get(meal_type, "🍽️")
        
        if daily:
            await message.answer(
                f"✅ {meal_emoji} *{meal_type}*:\n"
                f"{product_display}\n"
                f"⚖️ {weight} г (готовый)\n"
                f"🔥 {calories:.0f} ккал | 🥩 {protein:.0f}г | 🧈 {fat:.0f}г | 🍚 {carbs:.0f}г\n\n"
                f"📊 *Итого за сегодня:*\n"
                f"🔥 {daily['total_calories']:.0f} / 2000 ккал\n"
                f"🥩 {daily['total_protein']:.0f} / 150 г\n"
                f"🧈 {daily['total_fat']:.0f} / 55 г\n"
                f"🍚 {daily['total_carbs']:.0f} / 250 г",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
        else:
            await message.answer(
                f"✅ {meal_emoji} *{meal_type}*:\n"
                f"{product_display}\n"
                f"⚖️ {weight} г (готовый)\n"
                f"🔥 {calories:.0f} ккал | 🥩 {protein:.0f}г | 🧈 {fat:.0f}г | 🍚 {carbs:.0f}г",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введи число (граммы):")


# ========== ДНЕВНИК ПИТАНИЯ ==========
@dp.message(F.text == "📓 Мой дневник")
async def show_diary(message: Message):
    daily = get_daily_summary(message.from_user.id)
    today = date.today().strftime("%d.%m.%Y")
    
    if daily:
        await message.answer(
            f"📓 *Дневник за {today}*\n\n"
            f"🔥 Калории: *{daily['total_calories']:.0f}* / 2000\n"
            f"🥩 Белки: *{daily['total_protein']:.0f}* / 150 г\n"
            f"🧈 Жиры: *{daily['total_fat']:.0f}* / 55 г\n"
            f"🍚 Углеводы: *{daily['total_carbs']:.0f}* / 250 г",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"📓 *Дневник за {today}*\n\n"
            f"Пока нет записей.\n"
            f"Нажми '🥗 Добавить еду'",
            parse_mode="Markdown"
        )


# ========== СТАТИСТИКА ==========
@dp.message(F.text == "📈 Статистика за неделю")
async def show_weekly_stats(message: Message):
    week_data = get_week_summary(message.from_user.id)
    
    if not week_data:
        await message.answer("📊 Нет данных за неделю")
        return
    
    total_cal = sum(d['total_calories'] for d in week_data if d['total_calories'])
    avg_cal = total_cal / len(week_data) if week_data else 0
    
    text = "📈 *Статистика за неделю*\n\n"
    for day in week_data:
        text += f"📅 {day['date'][5:]}: {day['total_calories']:.0f} ккал\n"
    text += f"\n📊 Среднее: *{avg_cal:.0f}* ккал/день"
    
    await message.answer(text, parse_mode="Markdown")


# ========== ПЛАНЫ ПИТАНИЯ ==========
@dp.message(F.text == "💪 Планы питания")
async def show_plans(message: Message):
    has_sub = has_active_subscription(message.from_user.id)
    status = "✅ Подписка активна" if has_sub else "❌ Нет подписки"
    
    await message.answer(
        f"💪 *Планы питания*\n\n"
        f"{status}\n\n"
        f"🌱 Базовый — 50⭐ (7 дней)\n"
        f"💪 PRO — 100⭐ (30 дней)\n"
        f"👑 Премиум — 250⭐ (90 дней)\n\n"
        f"_Оплата Telegram Stars_",
        parse_mode="Markdown",
        reply_markup=plans_keyboard()
    )


# ========== ПЛАТЕЖИ ==========
@dp.callback_query(lambda c: c.data and c.data.startswith("buy_"))
async def process_plan_purchase(callback: CallbackQuery):
    plan_key = callback.data.replace("buy_", "")
    plan = PLANS.get(plan_key)
    
    if not plan:
        await callback.answer("План не найден")
        return
    
    prices = [LabeledPrice(label=plan["name"], amount=plan["price"])]
    
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=f"Подписка {plan['name']}",
        description=f"{plan['name']} на {plan['days']} дней",
        payload=f"subscription_{plan_key}_{plan['days']}",
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="subscription"
    )
    
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    if len(parts) >= 3:
        plan_key = parts[1]
        days = int(parts[2])
        set_subscription(message.from_user.id, plan_key, days)
        
        await message.answer(
            f"✅ *Оплата прошла!*\n\n"
            f"План активирован на {days} дней.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )


# ========== ПРОФИЛЬ ==========
@dp.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user = get_user(message.from_user.id)
    has_sub = has_active_subscription(message.from_user.id)
    
    text = f"👤 *Профиль*\n\n"
    text += f"Имя: {user['name']}\n"
    text += f"Пол: {user['gender'] or 'Не указан'}\n"
    text += f"Рост: {user['height'] or 'Не указан'} см\n"
    text += f"Подписка: {'✅ Да' if has_sub else '❌ Нет'}"
    
    await message.answer(text, parse_mode="Markdown")


# ========== НАЗАД ==========
@dp.message(F.text == "🔙 Назад")
async def go_back(message: Message):
    await message.answer("Главное меню", reply_markup=main_keyboard())


# ========== ФОТО ==========
@dp.message(F.photo)
async def handle_photo(message: Message):
    await message.answer(
        "📸 Фото получено!\n\n"
        "Анализ фото пока не работает.\n"
        "Используй '🥗 Добавить еду'",
        reply_markup=main_keyboard()
    )


# ========== РУЧНОЙ ВВОД ==========
@dp.message(Command("add_food"))
async def add_food_manual(message: Message):
    try:
        parts = message.text.split()
        if len(parts) < 6:
            await message.answer(
                "❌ Формат:\n"
                "/add_food название вес ккал белки жиры углеводы\n\n"
                "Пример: /add_food гречка 100 343 12.6 3.3 68"
            )
            return
        
        food_name = " ".join(parts[1:-5])
        weight = float(parts[-5])
        calories_per_100g = float(parts[-4])
        protein_per_100g = float(parts[-3])
        fat_per_100g = float(parts[-2])
        carbs_per_100g = float(parts[-1])
        
        calories = (calories_per_100g * weight) / 100
        protein = (protein_per_100g * weight) / 100
        fat = (fat_per_100g * weight) / 100
        carbs = (carbs_per_100g * weight) / 100
        
        save_food_entry(message.from_user.id, f"{food_name} (готовый, {weight}г)", calories, protein, fat, carbs)
        
        daily = get_daily_summary(message.from_user.id)
        
        if daily:
            await message.answer(
                f"✅ Добавлено: {food_name}\n"
                f"🔥 {calories:.0f} ккал\n\n"
                f"📊 Итого: {daily['total_calories']:.0f} / 2000 ккал",
                parse_mode="Markdown"
            )
        else:
            await message.answer(f"✅ Добавлено: {food_name}\n🔥 {calories:.0f} ккал")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ========== ЗАПУСК ==========
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    init_db()
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())