import sqlite3
from datetime import datetime, date
from contextlib import contextmanager

DATABASE_NAME = "fitness_bot.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        # Таблица пользователей
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                gender TEXT,
                height REAL,
                subscription_type TEXT,
                subscription_expires REAL
            )
        ''')
        
        # Таблица замеров (% жира)
        db.execute('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                neck REAL,
                waist REAL,
                hip REAL,
                fat_percent REAL
            )
        ''')
        
        # Таблица дневника питания (КБЖУ по дням)
        db.execute('''
            CREATE TABLE IF NOT EXISTS food_diary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                food_name TEXT,
                calories REAL,
                protein REAL,
                fat REAL,
                carbs REAL
            )
        ''')
        
        # Таблица дневных итогов
        db.execute('''
            CREATE TABLE IF NOT EXISTS daily_summary (
                user_id INTEGER,
                date TEXT,
                total_calories REAL,
                total_protein REAL,
                total_fat REAL,
                total_carbs REAL,
                PRIMARY KEY (user_id, date)
            )
        ''')

def get_user(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def save_user(user_id, name, gender=None, height=None):
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO users (user_id, name, gender, height)
            VALUES (?, ?, ?, ?)
        """, (user_id, name, gender, height))

def save_measurement(user_id, neck, waist, hip, fat_percent):
    with get_db() as db:
        db.execute("""
            INSERT INTO measurements (user_id, date, neck, waist, hip, fat_percent)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, date.today().isoformat(), neck, waist, hip, fat_percent))

def save_food_entry(user_id, food_name, calories, protein, fat, carbs):
    today = date.today().isoformat()
    with get_db() as db:
        db.execute("""
            INSERT INTO food_diary (user_id, date, food_name, calories, protein, fat, carbs)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, today, food_name, calories, protein, fat, carbs))
        
        # Обновляем дневную сумму
        db.execute("""
            INSERT INTO daily_summary (user_id, date, total_calories, total_protein, total_fat, total_carbs)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                total_calories = total_calories + excluded.total_calories,
                total_protein = total_protein + excluded.total_protein,
                total_fat = total_fat + excluded.total_fat,
                total_carbs = total_carbs + excluded.total_carbs
        """, (user_id, today, calories, protein, fat, carbs))

def get_daily_summary(user_id):
    today = date.today().isoformat()
    with get_db() as db:
        return db.execute("""
            SELECT * FROM daily_summary WHERE user_id = ? AND date = ?
        """, (user_id, today)).fetchone()

def get_week_summary(user_id):
    with get_db() as db:
        return db.execute("""
            SELECT date, total_calories, total_protein, total_fat, total_carbs
            FROM daily_summary
            WHERE user_id = ? AND date >= date('now', '-7 days')
            ORDER BY date DESC
        """, (user_id,)).fetchall()

def has_active_subscription(user_id):
    user = get_user(user_id)
    if not user or not user['subscription_expires']:
        return False
    expires = datetime.fromtimestamp(user['subscription_expires'])
    return expires > datetime.now()

def set_subscription(user_id, plan_type, days):
    expires = datetime.now().timestamp() + days * 86400
    with get_db() as db:
        db.execute("""
            UPDATE users SET subscription_type = ?, subscription_expires = ?
            WHERE user_id = ?
        """, (plan_type, expires, user_id))