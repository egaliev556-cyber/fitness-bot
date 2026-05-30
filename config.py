import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FATSECRET_KEY = os.getenv("FATSECRET_KEY")
FATSECRET_SECRET = os.getenv("FATSECRET_SECRET")

ADMIN_IDS = []

PLANS = {
    "basic": {"name": "🌱 Базовый план", "price": 50, "days": 7},
    "pro": {"name": "💪 PRO план", "price": 100, "days": 30},
    "premium": {"name": "👑 Премиум план", "price": 250, "days": 90}
}