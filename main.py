import asyncio
import sqlite3
from datetime import datetime, date, time, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ===== CONFIG =====
BOT_TOKEN = "8578925778:AAGmJhQphkHUxwND3TF_EeYgioywoERe8U4"  # o'zingizniki bilan almashtiring
ADMIN_ID = 958705445  # o'zgartiring
WORK_START_HOUR = 9
WORK_END_HOUR = 23
SLOT_MINUTES = 40
DB_PATH = "saltarosh.db"
# ==================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== DB =====
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    phone TEXT,
    start_iso TEXT,
    end_iso TEXT,
    status TEXT,
    created_at TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, 
    value TEXT
)""")
cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_working', '1')")
conn.commit()

# ===== FSM =====
class OrderStates(StatesGroup):
    waiting_for_time = State()
    waiting_for_phone = State()

# ===== Helpers =====
def admin_working() -> bool:
    cur.execute("SELECT value FROM settings WHERE key='admin_working'")
    row = cur.fetchone()
    return row and row[0] == "1"

def set_admin_working(flag: bool):
    cur.execute("UPDATE settings SET value=? WHERE key='admin_working'", ("1" if flag else "0",))
    conn.commit()

def generate_slots_for_day(target_date: date):
    """Berilgan kun uchun bo'sh slotlar ro'yxatini yaratadi,
       bugungi kun bo'lsa, faqat hozirgi vaqt va undan keyingi slotlarni chiqaradi."""
    slots = []
    now = datetime.now()
    current = datetime.combine(target_date, time(WORK_START_HOUR, 0))
    end_dt = datetime.combine(target_date, time(WORK_END_HOUR, 0))
    while current < end_dt:
        if target_date != date.today() or current >= now:
            slots.append(current)
        current += timedelta(minutes=SLOT_MINUTES)
    return slots

def is_slot_free(start_dt: datetime) -> bool:
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)
    cur.execute("SELECT start_iso, end_iso FROM orders WHERE status IN ('pending','approved')")
    rows = cur.fetchall()
    for s_iso, e_iso in rows:
        if not s_iso or not e_iso:
            continue
        s = datetime.fromisoformat(s_iso)
        e = datetime.fromisoformat(e_iso)
        if not (end_dt <= s or start_dt >= e):
            return False
    return True

def pretty_dt(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def normalize_phone(phone: str) -> str:
    phone = phone.strip()
    if phone.startswith('+'):
        prefix = '+'
        digits = ''.join(ch for ch in phone[1:] if ch.isdigit())
        return prefix + digits
    else:
        return ''.join(ch for ch in phone if ch.isdigit())

# ===== Keyboards =====
def client_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🕒 Soat tanlash")]],
        resize_keyboard=True
    )

def admin_kb():
    buttons = [[KeyboardButton(text="🧾 Buyurtmalar")]]
    if admin_working():
        buttons.append([KeyboardButton(text="🚪 Ishdan chiqish")])
    else:
        buttons.append([KeyboardButton(text="✅ Ishga kirish")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ===== Client /start =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panel:", reply_markup=admin_kb())
    else:
        await message.answer(
            "💈 Sartaroshxona botiga xush kelibsiz!\nVaqt tanlash uchun bosing:",
            reply_markup=client_kb()
        )

# ===== Client: slot tanlash =====
@dp.message(F.text == "🕒 Soat tanlash")
async def choose_time(message: types.Message, state: FSMContext):
    if not admin_working():
        await message.answer("🚫 Sartarosh hozir ishlamayapti.")
        return

    today = date.today()
    slots = generate_slots_for_day(today)

    buttons = []
    for s in slots:
        if is_slot_free(s):
            buttons.append([InlineKeyboardButton(text=pretty_dt(s), callback_data=f"slot_{s.isoformat()}")])

    if not buttons:
        await message.answer("Bugun bo‘sh vaqt yo‘q.")
        return

    await message.answer("Bo‘sh vaqtni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(OrderStates.waiting_for_time)

# ===== Callback: slot tanlandi =====
@dp.callback_query(F.data.startswith("slot_"))
async def slot_chosen(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    iso = callback.data[5:]
    try:
        start_dt = datetime.fromisoformat(iso)
    except Exception:
        await callback.message.answer("Xato: tanlangan vaqt noto'g'ri. Qayta tanlang.")
        return

    if not is_slot_free(start_dt):
        await callback.message.answer("Afsus, bu slot band boʻlib qolgan. Boshqasini tanlang.")
        return

    await state.update_data(start_iso=iso)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📲 Telefonni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer("📞 Iltimos, telefon raqamingizni yuboring (yoki tugma orqali ulashing):", reply_markup=kb)
    await state.set_state(OrderStates.waiting_for_phone)

# ===== Client: telefon raqami =====
@dp.message(OrderStates.waiting_for_phone)
async def got_phone(message: types.Message, state: FSMContext):
    phone = None
    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
    elif message.text:
        phone = message.text.strip()
    else:
        await message.answer("Iltimos, telefon raqamingizni yuboring (kontakt yoki raqam sifatida).")
        return

    phone = normalize_phone(phone)
    if len(phone) < 5:
        await message.answer("Iltimos, to'g'ri telefon raqamini yuboring.")
        return

    data = await state.get_data()
    start_iso = data.get("start_iso")
    if not start_iso:
        await message.answer("Xatolik: boshlang'ich vaqt topilmadi. Iltimos, boshidan /start qilib qayta urinib ko'ring.")
        await state.clear()
        return

    start_dt = datetime.fromisoformat(start_iso)
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)

    if not is_slot_free(start_dt):
        await message.answer("Afsus, tanlangan vaqt boshqa mijoz tomonidan band qilindi. Boshqa vaqt tanlang.")
        await state.clear()
        return

    cur.execute(
        "INSERT INTO orders (user_id, phone, start_iso, end_iso, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (message.from_user.id, phone, start_iso, end_dt.isoformat(), "pending", datetime.now().isoformat())
    )
    conn.commit()
    oid = cur.lastrowid

    await bot.send_message(
        ADMIN_ID,
        f"🆕 Yangi buyurtma (ID: {oid}):\nTel: {phone}\nVaqt: {pretty_dt(start_dt)} — {pretty_dt(end_dt)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"approve_{oid}"),
             InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{oid}")]
        ])
    )

    await message.answer(f"✅ Buyurtmangiz qabul qilindi. Vaqtingiz: {pretty_dt(start_dt)} — {pretty_dt(end_dt)}\nSartarosh tasdiqlaguncha kuting.", reply_markup=client_kb())
    await state.clear()

# ===== Admin tasdiqlash / rad etish =====
@dp.callback_query(F.data.startswith("approve_"))
async def approve(callback: types.CallbackQuery):
    await callback.answer()
    try:
        oid = int(callback.data.split("_")[1])
    except:
        await callback.message.edit_text("Xato: noto'g'ri buyurtma ID.")
        return

    cur.execute("SELECT user_id, start_iso, end_iso, status FROM orders WHERE id=?", (oid,))
    row = cur.fetchone()
    if not row:
        await callback.message.edit_text("Buyurtma topilmadi.")
        return

    user_id, s_iso, e_iso, status = row
    if status == "approved":
        await callback.answer("Bu buyurtma allaqachon tasdiqlangan.", show_alert=True)
        await callback.message.edit_text("✅ (Allaqachon tasdiqlangan)")
    else:
        cur.execute("UPDATE orders SET status='approved' WHERE id=?", (oid,))
        conn.commit()
        s = pretty_dt(datetime.fromisoformat(s_iso))
        e = pretty_dt(datetime.fromisoformat(e_iso))
        try:
            await bot.send_message(user_id, f"✅ Buyurtmangiz tasdiqlandi!\nVaqtingiz: {s} — {e}")
        except Exception as ex:
            await callback.message.reply(f"⚠️ Klientga xabar yuborib bo'lmadi: {ex}")
        await callback.message.edit_text("✅ Buyurtma tasdiqlandi.")
        await callback.answer("Tasdiqlandi")

@dp.callback_query(F.data.startswith("reject_"))
async def reject(callback: types.CallbackQuery):
    await callback.answer()
    try:
        oid = int(callback.data.split("_")[1])
    except:
        await callback.message.edit_text("Xato: noto'g'ri buyurtma ID.")
        return

    cur.execute("SELECT user_id, status FROM orders WHERE id=?", (oid,))
    row = cur.fetchone()
    if not row:
        await callback.message.edit_text("Buyurtma topilmadi.")
        return

    user_id, status = row
    if status == "rejected":
        await callback.answer("Bu buyurtma allaqachon rad etilgan.", show_alert=True)
        await callback.message.edit_text("❌ (Allaqachon rad etilgan)")
    else:
        cur.execute("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
        conn.commit()
        try:
            await bot.send_message(user_id, "❌ Afsuski, buyurtmangiz rad etildi. Boshqa vaqtni tanlang.")
        except Exception as ex:
            await callback.message.reply(f"⚠️ Klientga xabar yuborib bo'lmadi: {ex}")
        await callback.message.edit_text("❌ Buyurtma rad etildi.")
        await callback.answer("Rad etildi")

# ===== Admin panel =====
@dp.message(F.text.in_({"🧾 Buyurtmalar", "🚪 Ishdan chiqish", "✅ Ishga kirish"}))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text == "🧾 Buyurtmalar":
        today = date.today().isoformat()
        cur.execute("SELECT id, phone, start_iso, end_iso, status FROM orders WHERE date(start_iso)=? ORDER BY start_iso", (today,))
        rows = cur.fetchall()
        if not rows:
            await message.answer("Bugun buyurtmalar yo‘q.")
            return
        for oid, phone, s_iso, e_iso, status in rows:
            s = pretty_dt(datetime.fromisoformat(s_iso))
            e = pretty_dt(datetime.fromisoformat(e_iso))
            txt = f"ID: {oid}\nTel: {phone}\nVaqt: {s} — {e}\nHolat: {status.upper()}"
            kb = None
            if status == "pending":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Qabul", callback_data=f"approve_{oid}"),
                     InlineKeyboardButton(text="❌ Rad", callback_data=f"reject_{oid}")]
                ])
            await message.answer(txt, reply_markup=kb)
    elif message.text == "🚪 Ishdan chiqish":
        set_admin_working(False)
        await message.answer("⛔ Endi mijozlar vaqt tanlay olmaydi.", reply_markup=admin_kb())
    elif message.text == "✅ Ishga kirish":
        set_admin_working(True)
        await message.answer("✅ Mijozlar yana vaqt tanlashi mumkin.", reply_markup=admin_kb())

# ===== Fallback =====
@dp.message()
async def fallback(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panel:", reply_markup=admin_kb())
    else:
        await message.answer("Iltimos, menyudan tanlang yoki /start bosing.")

# ===== Start =====
async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
