import asyncio
import sqlite3
import os
import pandas as pd
import hashlib
import random
import string
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
from config import TOKEN, ADMIN_ID, SBP_NUMBER, USDT_WALLET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot.db")
REF_PATH = os.path.join(BASE_DIR, "referal.db")
BASES_DIR = os.path.join(BASE_DIR, "bases")

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ========== БАЗА ДАННЫХ ==========
def init_db():
    os.makedirs(BASES_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY,
                      free_dox_requests INTEGER DEFAULT 3,
                      full_paid_requests INTEGER DEFAULT 0,
                      username TEXT,
                      reg_date INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      amount INTEGER,
                      currency TEXT,
                      requests INTEGER,
                      status TEXT,
                      payment_id TEXT UNIQUE,
                      date INTEGER)''')
        conn.commit()
    with sqlite3.connect(REF_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS referals
                     (user_id INTEGER PRIMARY KEY,
                      referer_id INTEGER,
                      referal_code TEXT UNIQUE,
                      level1 INTEGER DEFAULT 0,
                      earnings INTEGER DEFAULT 0)''')
        conn.commit()


def register_user(user_id, username, referal_code=None):
    referer_id = None
    if referal_code:
        with sqlite3.connect(REF_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id FROM referals WHERE referal_code = ?", (referal_code,))
            row = c.fetchone()
            if row:
                referer_id = row[0]
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date) VALUES (?, ?, ?)",
                  (user_id, username, int(datetime.now().timestamp())))
        conn.commit()
    if referer_id and referer_id != user_id:
        with sqlite3.connect(REF_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO referals (user_id, referer_id, referal_code) VALUES (?, ?, ?)",
                      (user_id, referer_id, generate_code(user_id)))
            c.execute("UPDATE referals SET level1 = level1 + 1 WHERE user_id = ?", (referer_id,))
            conn.commit()


def generate_code(user_id):
    return f"TRAY{user_id}{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"


def get_referal_link(user_id):
    with sqlite3.connect(REF_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT referal_code FROM referals WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row:
            return f"https://t.me/Trayanovsy_bot?start={row[0]}"
        code = generate_code(user_id)
        c.execute("INSERT INTO referals (user_id, referal_code) VALUES (?, ?)", (user_id, code))
        conn.commit()
        return f"https://t.me/Trayanovsy_bot?start={code}"


def get_referal_stats(user_id):
    with sqlite3.connect(REF_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT level1 FROM referals WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else 0


def get_free_dox_requests(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT free_dox_requests FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else 3


def get_full_paid_requests(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT full_paid_requests FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else 0


def use_free_dox(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE users SET free_dox_requests = free_dox_requests - 1 WHERE user_id = ? AND free_dox_requests > 0",
            (user_id,))
        return c.rowcount > 0


def use_full_paid(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE users SET full_paid_requests = full_paid_requests - 1 WHERE user_id = ? AND full_paid_requests > 0",
            (user_id,))
        return c.rowcount > 0


def add_full_paid_requests(user_id, amount):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET full_paid_requests = full_paid_requests + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()


def create_payment(user_id, amount, currency, requests, payment_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO payments (user_id, amount, currency, requests, status, payment_id, date) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (user_id, amount, currency, requests, payment_id, int(datetime.now().timestamp())))
        conn.commit()


def confirm_payment(payment_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, requests FROM payments WHERE payment_id = ? AND status = 'pending'", (payment_id,))
        row = c.fetchone()
        if row:
            user_id, requests = row
            c.execute("UPDATE payments SET status = 'completed' WHERE payment_id = ?", (payment_id,))
            conn.commit()
            add_full_paid_requests(user_id, requests)
            return user_id, requests
    return None, 0


# ========== ПОИСК В БАЗАХ ==========
def search_in_bases(query):
    if not os.path.exists(BASES_DIR):
        return None
    for file in os.listdir(BASES_DIR):
        if file.endswith(".csv"):
            try:
                df = pd.read_csv(os.path.join(BASES_DIR, file), dtype=str)
                for col in df.columns:
                    mask = df[col].astype(str).str.contains(query, case=False, na=False)
                    if mask.any():
                        return df[mask].iloc[0].to_dict()
            except:
                pass
    return None


def format_free_dox(data):
    if not data:
        return "❌ *ДОКС НЕ НАЙДЕН*\n\n📌 Проверь правильность ввода"
    text = "┌─────────────────────────────────────────┐\n"
    text += "│         🔍 *ДОКС (БЕСПЛАТНО)* 🔍        │\n"
    text += "├─────────────────────────────────────────┤\n"
    text += f"│ 👤 ФИО: {data.get('full_name', data.get('ФИО', '—'))}\n"
    text += f"│ 📞 Телефон: {data.get('phone', data.get('номер', '—'))}\n"
    text += f"│ 👩 Мать: {data.get('mother_name', data.get('мать', '—'))}\n"
    text += f"│ 👨 Отец: {data.get('father_name', data.get('отец', '—'))}\n"
    text += "└─────────────────────────────────────────┘\n"
    text += "\n👇 *Для ПОЛНОГО ОТЧЁТА (адрес, паспорт, IP, работа, соцсети) нажми ниже* 👇"
    return text


def format_full_report(data):
    if not data:
        return "❌ *ДАННЫЕ НЕ НАЙДЕНЫ*"
    text = "┌─────────────────────────────────────────┐\n"
    text += "│         💀 *ПОЛНЫЙ ОТЧЁТ* 💀            │\n"
    text += "├─────────────────────────────────────────┤\n"
    fields = {
        "👤 ФИО": data.get("full_name", data.get("ФИО", "—")),
        "📞 Телефон": data.get("phone", data.get("номер", "—")),
        "📍 Адрес": data.get("address", data.get("адрес", "—")),
        "🎂 Дата рождения": data.get("birth_date", data.get("дата рождения", "—")),
        "👩 Мать": data.get("mother_name", data.get("мать", "—")),
        "👨 Отец": data.get("father_name", data.get("отец", "—")),
        "🪪 Паспорт": data.get("passport", data.get("паспорт", "—")),
        "💻 IP-адрес": data.get("ip", data.get("IP", "—")),
        "🏢 Место работы": data.get("job", data.get("работа", "—")),
        "🌐 Соцсети": data.get("social", data.get("соцсети", "—")),
        "🚗 Автомобиль": data.get("car", data.get("авто", "—")),
        "🏠 Недвижимость": data.get("property", data.get("недвижимость", "—"))
    }
    for label, value in fields.items():
        if value and value != "—":
            text += f"│ {label}: {value}\n"
    text += "└─────────────────────────────────────────┘\n"
    text += "✅ Полный отчёт сформирован."
    return text


# ========== ПРИВЕТСТВИЕ ==========
WELCOME_TEXT = """
🔎 *Поисковая система.*

Добро пожаловать, агент!

Ваш ID: `{user_id}`

🎁 Бесплатных докс-запросов: {free_dox}/3
💰 Платных (полный отчёт): {full_paid}

📅 Дата регистрации: {reg_date}

💀 *3 бесплатных докса* (ФИО, телефон, родители)
💎 *Полный отчёт* — адрес, паспорт, IP, работа, соцсети — платно

👇 /menu
"""

EXAMPLES_TEXT = """
ℹ️ *Примеры для ввода команд*

🕵️ *Личность:*
`Иванов Иван Иванович 15.05.1985`

📲 *Контакты:*
`89224030705` – номер телефона

💬 *Социальные сети:*
`@ivanov` – Telegram

📸 Отправьте лицо человека, чтобы попробовать найти его.
"""

REFERAL_TEXT = """
🤝 *Партнёрская программа:*

🎁 За каждого приглашённого: +5 платных запросов

🔗 Твоя ссылка: {link}

👥 Приглашено: {count}
💰 Заработано запросов: {earned}
"""

main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔍 БЕСПЛАТНЫЙ ДОКС", callback_data="free_dox")],
    [InlineKeyboardButton(text="💎 ПОЛНЫЙ ОТЧЁТ (ПЛАТНО)", callback_data="full_report")],
    [InlineKeyboardButton(text="💀 СНОС АККАУНТА", callback_data="snos")],
    [InlineKeyboardButton(text="💰 КУПИТЬ ЗАПРОСЫ", callback_data="buy")],
    [InlineKeyboardButton(text="⭐ БАЛАНС", callback_data="balance")],
    [InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="referal")],
])

buy_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📦 10 полных отчётов — 350₽", callback_data="buy_10")],
    [InlineKeyboardButton(text="📦 50 полных отчётов — 1500₽", callback_data="buy_50")],
    [InlineKeyboardButton(text="📦 100 полных отчётов — 2500₽", callback_data="buy_100")],
    [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu")],
])

payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💳 СБП", callback_data="pay_sbp")],
    [InlineKeyboardButton(text="₿ USDT", callback_data="pay_usdt")],
    [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="buy")],
])


@dp.message(CommandStart())
async def start(message: types.Message):
    args = message.text.split()
    ref = args[1] if len(args) > 1 else None
    register_user(message.from_user.id, message.from_user.username, ref)
    user_id = message.from_user.id
    free_dox = get_free_dox_requests(user_id)
    full_paid = get_full_paid_requests(user_id)
    reg_ts = 0
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT reg_date FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row:
            reg_ts = row[0]
    reg_date_str = datetime.fromtimestamp(reg_ts).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        WELCOME_TEXT.format(user_id=user_id, free_dox=free_dox, full_paid=full_paid, reg_date=reg_date_str),
        parse_mode="Markdown")
    await message.answer(EXAMPLES_TEXT, parse_mode="Markdown")


@dp.message(Command("menu"))
async def menu_cmd(message: types.Message):
    await message.answer("💀 *ГЛАВНОЕ МЕНЮ*", reply_markup=main_menu, parse_mode="Markdown")


@dp.message(Command("balance"))
async def balance_cmd(message: types.Message):
    free_dox = get_free_dox_requests(message.from_user.id)
    full_paid = get_full_paid_requests(message.from_user.id)
    await message.answer(f"⭐ *БАЛАНС*\n\n🔍 Бесплатных доксов: {free_dox}/3\n💎 Платных полных отчётов: {full_paid}",
                         parse_mode="Markdown")


@dp.message(Command("buy"))
async def buy_cmd(message: types.Message):
    await message.answer("💎 *ВЫБЕРИ ПАКЕТ*", reply_markup=buy_keyboard, parse_mode="Markdown")


@dp.message(Command("referal"))
async def referal_cmd(message: types.Message):
    link = get_referal_link(message.from_user.id)
    count = get_referal_stats(message.from_user.id)
    await message.answer(REFERAL_TEXT.format(link=link, count=count, earned=count * 5), parse_mode="Markdown")


@dp.callback_query()
async def callback_handler(call: types.CallbackQuery):
    if call.data == "menu":
        await call.message.edit_text("💀 *ГЛАВНОЕ МЕНЮ*", reply_markup=main_menu, parse_mode="Markdown")
    elif call.data == "free_dox":
        await call.message.answer(
            "🔍 *ВВЕДИ ФИО ИЛИ НОМЕР ДЛЯ БЕСПЛАТНОГО ДОКСА*\n\n📌 Найдётся: ФИО, телефон, родители")
    elif call.data == "full_report":
        paid = get_full_paid_requests(call.from_user.id)
        if paid > 0:
            await call.message.answer(
                "💎 *ВВЕДИ ФИО ИЛИ НОМЕР ДЛЯ ПОЛНОГО ОТЧЁТА*\n\n📌 Будет найдено: адрес, паспорт, IP, работа, соцсети")
        else:
            await call.message.answer("❌ *НЕТ ПЛАТНЫХ ЗАПРОСОВ*\n\nКупи пакет: /buy")
    elif call.data == "snos":
        await call.message.answer("💀 *СНОС АККАУНТА*\n\nВведи @username цели\n💰 Стоимость: 1 полный отчёт (50₽)")
    elif call.data == "balance":
        free_dox = get_free_dox_requests(call.from_user.id)
        full_paid = get_full_paid_requests(call.from_user.id)
        await call.message.edit_text(
            f"⭐ *БАЛАНС*\n\n🔍 Бесплатных доксов: {free_dox}/3\n💎 Платных полных отчётов: {full_paid}",
            reply_markup=main_menu, parse_mode="Markdown")
    elif call.data == "referal":
        link = get_referal_link(call.from_user.id)
        count = get_referal_stats(call.from_user.id)
        await call.message.edit_text(REFERAL_TEXT.format(link=link, count=count, earned=count * 5),
                                     reply_markup=main_menu, parse_mode="Markdown")
    elif call.data == "buy":
        await call.message.edit_text("💎 *ВЫБЕРИ ПАКЕТ*", reply_markup=buy_keyboard, parse_mode="Markdown")
    elif call.data.startswith("buy_"):
        pkg = call.data.split("_")[1]
        if pkg == "10":
            amount, reqs = 350, 10
        elif pkg == "50":
            amount, reqs = 1500, 50
        else:
            amount, reqs = 2500, 100
        call.bot.data = {"amount": amount, "requests": reqs}
        await call.message.edit_text(f"💰 *ОПЛАТА {amount}₽*", reply_markup=payment_keyboard, parse_mode="Markdown")
    elif call.data in ["pay_sbp", "pay_usdt"]:
        amount = call.bot.data.get("amount", 350)
        reqs = call.bot.data.get("requests", 10)
        user_id = call.from_user.id
        pay_id = hashlib.md5(f"{user_id}{amount}{datetime.now().timestamp()}".encode()).hexdigest()[:16]
        create_payment(user_id, amount, call.data, reqs, pay_id)
        if call.data == "pay_sbp":
            text = f"💳 *СБП ОПЛАТА*\nСумма: {amount}₽\nКарта: `{SBP_NUMBER}`\n\n✅ ПОСЛЕ ОПЛАТЫ НАЖМИ КНОПКУ"
        else:
            text = f"₿ *USDT ОПЛАТА*\nСумма: {amount}₽\nКошелёк: `{USDT_WALLET}`\n\n✅ ПОСЛЕ ОПЛАТЫ НАЖМИ КНОПКУ"
        confirm = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✅ Я ОПЛАТИЛ", callback_data=f"check_{pay_id}")]])
        await call.message.edit_text(text, reply_markup=confirm, parse_mode="Markdown")
    elif call.data.startswith("check_"):
        pay_id = call.data.replace("check_", "")
        uid, reqs = confirm_payment(pay_id)
        if uid:
            await call.message.edit_text(f"✅ *ОПЛАТА ПОДТВЕРЖДЕНА!*\n+{reqs} полных отчётов", parse_mode="Markdown")
            await bot.send_message(ADMIN_ID, f"💰 ОПЛАТА\n👤 {uid}\n💸 {call.bot.data.get('amount', 0)}₽")
        else:
            await call.message.answer("❌ Платёж не найден")
    await call.answer()


@dp.message()
async def text_handler(message: types.Message):
    user_id = message.from_user.id
    query = message.text.strip()

    # Снос аккаунта
    if query.startswith("@"):
        full_paid = get_full_paid_requests(user_id)
        if full_paid > 0:
            use_full_paid(user_id)
            await message.answer(
                f"💀 *СНОС АККАУНТА {query}*\nЖалоба отправлена. Осталось полных отчётов: {get_full_paid_requests(user_id)}",
                parse_mode="Markdown")
        else:
            await message.answer("❌ *НЕТ ЗАПРОСОВ ДЛЯ СНОСА*\nКупи: /buy", parse_mode="Markdown")
        return

    # Поиск данных
    data = search_in_bases(query)

    # Проверяем, хочет ли пользователь полный отчёт (если есть платные запросы)
    full_paid = get_full_paid_requests(user_id)
    if full_paid > 0:
        use_full_paid(user_id)
        await message.answer("💎 *ПОЛНЫЙ ОТЧЁТ (ПЛАТНЫЙ)*", parse_mode="Markdown")
        await message.answer(format_full_report(data), parse_mode="Markdown")
    else:
        free_dox = get_free_dox_requests(user_id)
        if free_dox > 0:
            use_free_dox(user_id)
            text = format_free_dox(data)
            upgrade_btn = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 ОТКРЫТЬ ПОЛНЫЙ ОТЧЁТ (50₽)", callback_data="buy")],
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu")]
            ])
            await message.answer(text, reply_markup=upgrade_btn, parse_mode="Markdown")
        else:
            await message.answer("❌ *НЕТ ЗАПРОСОВ*\n\n🎁 Бесплатные доксы кончились. Купи полные отчёты: /buy",
                                 parse_mode="Markdown")


# ========== АДМИН-КОМАНДЫ ==========
@dp.message(Command("stats"))
async def stats_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT SUM(full_paid_requests) FROM users")
        paid = c.fetchone()[0] or 0
        await message.answer(f"📊 *СТАТИСТИКА*\n👥 Users: {users}\n💎 Платных отчётов: {paid}", parse_mode="Markdown")


@dp.message(Command("add_requests"))
async def add_req_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ /add_requests USER_ID КОЛИЧЕСТВО")
        return
    uid, amt = int(args[1]), int(args[2])
    add_full_paid_requests(uid, amt)
    await message.answer(f"✅ +{amt} полных отчётов → {uid}")


async def main():
    init_db()
    await bot.set_my_commands([BotCommand(command="menu", description="Главное меню")])
    print("=" * 40)
    print("🔥 ТРАЯНОВСКИЙ DOX SYSTEM ЗАПУЩЕН")
    print(f"👑 АДМИН: {ADMIN_ID}")
    print(f"📁 БАЗЫ: {BASES_DIR}")
    print("=" * 40)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())