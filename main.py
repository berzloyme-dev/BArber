import asyncio
import sqlite3
from datetime import datetime, date, time, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ===== CONFIG =====
BOT_TOKEN = "8578925778:AAGmJhQphkHUxwND3TF_EeYgioywoERe8U4"
ADMIN_ID = 8130394571

WORK_START_HOUR = 9
WORK_END_HOUR = 23
SLOT_MINUTES = 40

# 📍 STATIK LOKATSIYA (SEN BERGAN)
SHOP_LAT = 40.417889
SHOP_LON = 71.507999

DB_PATH = "sartarosh.db"
# ==================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== DB =====
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    phone TEXT,
    start_iso TEXT,
    end_iso TEXT,
    location TEXT,
    status TEXT,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

cur.execute("INSERT OR IGNORE INTO settings VALUES ('admin_working','1')")
conn.commit()

# ===== FSM =====
class OrderStates(StatesGroup):
    waiting_for_time = State()
    waiting_for_phone = State()

# ===== HELPERS =====
def admin_working():
    cur.execute("SELECT value FROM settings WHERE key='admin_working'")
    return cur.fetchone()[0] == "1"

def set_admin_working(flag: bool):
    cur.execute(
        "UPDATE settings SET value=? WHERE key='admin_working'",
        ("1" if flag else "0",)
    )
    conn.commit()

def generate_slots_for_day(target_date: date):
    slots = []
    now = datetime.now().replace(second=0, microsecond=0)

    current = datetime.combine(target_date, time(WORK_START_HOUR, 0))
    end_dt = datetime.combine(target_date, time(WORK_END_HOUR, 0))

    while current < end_dt:
        if target_date > date.today() or current > now:
            slots.append(current)
        current += timedelta(minutes=SLOT_MINUTES)

    return slots

def is_slot_free(start_dt: datetime):
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)
    cur.execute("SELECT start_iso, end_iso FROM orders WHERE status IN ('pending','approved')")
    for s, e in cur.fetchall():
        s, e = datetime.fromisoformat(s), datetime.fromisoformat(e)
        if not (end_dt <= s or start_dt >= e):
            return False
    return True

def pretty(dt: datetime):
    return dt.strftime("%H:%M")

# ===== KEYBOARDS =====
def client_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕒 Soat tanlash")],
            [KeyboardButton(text="📍 Sartaroshxona joyi")]
        ],
        resize_keyboard=True
    )

def admin_kb():
    kb = [[KeyboardButton(text="🧾 Buyurtmalar")]]
    kb.append([KeyboardButton(
        text="🚪 Ishdan chiqish" if admin_working() else "✅ Ishga kirish"
    )])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ===== START =====
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panel", reply_markup=admin_kb())
    else:
        await message.answer(
            "💈 Sartaroshxona botiga xush kelibsiz",
            reply_markup=client_kb()
        )

# ===== STATIK LOKATSIYA BUTTON =====
@dp.message(F.text == "📍 Sartaroshxona joyi")
async def show_location(message: types.Message):
    await bot.send_location(
        chat_id=message.chat.id,
        latitude=SHOP_LAT,
        longitude=SHOP_LON
    )

# ===== TIME CHOOSE =====
@dp.message(F.text == "🕒 Soat tanlash")
async def choose_time(message: types.Message, state: FSMContext):
    if not admin_working():
        await message.answer("🚫 Hozir ishlamaymiz")
        return

    cur.execute(
        "SELECT 1 FROM orders WHERE user_id=? AND status IN ('pending','approved')",
        (message.from_user.id,)
    )
    if cur.fetchone():
        await message.answer("❗ Sizda allaqachon faol buyurtma bor")
        return

    slots = generate_slots_for_day(date.today())
    buttons = []

    for s in slots:
        if is_slot_free(s):
            buttons.append([
                InlineKeyboardButton(
                    text=pretty(s),
                    callback_data=f"slot_{s.isoformat()}"
                )
            ])

    if not buttons:
        await message.answer("Bugun bo‘sh vaqt yo‘q")
        return

    await message.answer(
        "Bo‘sh vaqtni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(OrderStates.waiting_for_time)

# ===== SLOT CALLBACK =====
@dp.callback_query(F.data.startswith("slot_"))
async def slot_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    start_iso = callback.data[5:]
    await state.update_data(start_iso=start_iso)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📲 Telefon yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await callback.message.answer(
        "📞 Telefon raqamingizni yuboring:",
        reply_markup=kb
    )
    await state.set_state(OrderStates.waiting_for_phone)

# ===== PHONE =====
@dp.message(OrderStates.waiting_for_phone)
async def phone_step(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    data = await state.get_data()

    start_dt = datetime.fromisoformat(data["start_iso"])
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)

    cur.execute(
        "INSERT INTO orders (user_id, phone, start_iso, end_iso, location, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            message.from_user.id,
            phone,
            start_dt.isoformat(),
            end_dt.isoformat(),
            f"{SHOP_LAT},{SHOP_LON}",
            "pending",
            datetime.now().isoformat()
        )
    )
    conn.commit()

    await message.answer(
        f"✅ Buyurtma qabul qilindi\n⏰ {pretty(start_dt)} - {pretty(end_dt)}",
        reply_markup=client_kb()
    )
    await state.clear()

# ===== ADMIN =====
@dp.message(F.text == "🧾 Buyurtmalar")
async def orders_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cur.execute("SELECT phone,start_iso,location,status FROM orders ORDER BY start_iso")
    rows = cur.fetchall()

    if not rows:
        await message.answer("Buyurtmalar yo‘q")
        return

    for phone, s, loc, status in rows:
        lat, lon = loc.split(",")
        await message.answer(
            f"📞 {phone}\n"
            f"⏰ {pretty(datetime.fromisoformat(s))}\n"
            f"📍 https://maps.google.com/?q={lat},{lon}\n"
            f"📌 {status}"
        )

@dp.message(F.text == "🚪 Ishdan chiqish")
async def off(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        set_admin_working(False)
        await message.answer("⛔ O‘chirildi", reply_markup=admin_kb())

@dp.message(F.text == "✅ Ishga kirish")
async def on(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        set_admin_working(True)
        await message.answer("✅ Yoqildi", reply_markup=admin_kb())

# ===== RUN =====
async def main():
    print("Bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
