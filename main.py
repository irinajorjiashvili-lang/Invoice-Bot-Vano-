import os
import telebot
from datetime import datetime
from telebot import types
import requests
import time
import threading

os.environ['PYTHONUNBUFFERED'] = '1'
print("🚀 Auto Invoice Bot starting...")

BOT_TOKEN  = os.environ.get('BOT_TOKEN', '8760516717:AAH6q12ZZZujNdW6XQh8aigZGVOO4fUSQwo')
BOT_PASSWORD = os.environ.get('BOT_PASSWORD', 'Hybridi2026')
bot = telebot.TeleBot(BOT_TOKEN)
user_state = {}

GOOGLE_FORM_SUBMIT_URL  = "https://docs.google.com/forms/d/1wOP-nAS7h8y8r4L6ezeaNow2v9XVGkQ3mOamzX-dLKA/formResponse"
GOOGLE_DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1_MYLYCzkXrrG8FJzW8JazWHTXdS2sgC4"

GOOGLE_FORM_FIELDS = {
    'Date_Year':     'entry.2136135204_year',
    'Date_Month':    'entry.2136135204_month',
    'Date_Day':      'entry.2136135204_day',
    'Customer_Name': 'entry.21018057',
    'Customer_ID':   'entry.1116307930',
    'Lot':           'entry.1163357354',
    'Vehicle':       'entry.341377459',
    'Vin':           'entry.1094744061',
    'Amount_USD':    'entry.1342000086',
    'Auction_Fee':   'entry.532543637',
    'Total_USD':     'entry.857168306',
    'Buyer':         'entry.784567376'
}

INPUT_TEMPLATE = (
    "📋 Отправьте данные одним сообщением, каждый с новой строки:\n\n"
    "LOT\n"
    "VIN\n"
    "Авто (год марка модель)\n"
    "Amount USD\n"
    "Buyer\n"
    "Имя клиента\n"
    "ID клиента\n"
    "Auction Fee"
)


def safe_send(chat_id, text, reply_markup=None):
    for attempt in range(3):
        try:
            return bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def submit_to_google_form(data):
    try:
        form_data = {entry_id: str(data[field])
                     for field, entry_id in GOOGLE_FORM_FIELDS.items()
                     if field in data and data[field]}
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        print(f"[FORM] Отправляю: {form_data}")
        r = requests.post(GOOGLE_FORM_SUBMIT_URL, data=form_data, headers=headers,
                          allow_redirects=True, timeout=15)
        print(f"[FORM] HTTP {r.status_code} | {r.text[:200]}")
        return r.status_code in [200, 302, 400]
    except Exception as e:
        print(f"[FORM] error: {e}")
        return False


def send_completion(chat_id, data):
    msg = (
        "✅ Отправлено\n\n"
        f"📅 {data['Date_Day']}.{data['Date_Month']}.{data['Date_Year']}\n"
        f"🚗 Lot: {data['Lot']}\n"
        f"🔢 VIN: {data['Vin']}\n"
        f"🚙 {data['Vehicle']}\n"
        f"🏢 Buyer: {data['Buyer']}\n"
        f"👤 {data['Customer_Name']} ({data['Customer_ID']})\n"
        f"💰 Amount: ${data['Amount_USD']}\n"
        f"💸 Fee: ${data['Auction_Fee']}\n"
        f"💵 Total: ${data['Total_USD']}\n\n"
        f"📁 Документы (1-3 мин):\n{GOOGLE_DRIVE_FOLDER_URL}"
    )
    safe_send(chat_id, msg)

    def reminder():
        time.sleep(120)
        safe_send(chat_id, f"⏰ Проверьте документы:\n{GOOGLE_DRIVE_FOLDER_URL}")

    threading.Thread(target=reminder, daemon=True).start()


def start_input(chat_id):
    user_state[chat_id] = {
        'auth': True,
        'waiting_for': 'bulk',
    }
    safe_send(chat_id, INPUT_TEMPLATE)


def parse_bulk(lines):
    try:
        amount = float(lines[3].replace(',', '').replace('$', '').replace(' ', ''))
        fee    = float(lines[7].replace(',', '').replace(' ', ''))
        now = datetime.now()
        return {
            'Date_Year':     str(now.year),
            'Date_Month':    str(now.month),
            'Date_Day':      str(now.day),
            'Lot':           lines[0],
            'Vin':           lines[1],
            'Vehicle':       lines[2],
            'Amount_USD':    str(amount),
            'Buyer':         lines[4],
            'Customer_Name': lines[5],
            'Customer_ID':   lines[6],
            'Auction_Fee':   str(fee),
            'Total_USD':     str(round(amount + fee, 2)),
        }
    except Exception:
        return None


# ── Handlers ───────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['document', 'photo'])
def handle_file(message):
    chat_id = message.chat.id
    if not user_state.get(chat_id, {}).get('auth'):
        user_state[chat_id] = {'auth': False}
        safe_send(chat_id, "🔒 Введите пароль:")
        return
    start_input(chat_id)


@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text    = message.text.strip()

    if text.startswith('/start'):
        user_state[chat_id] = {'auth': False}
        safe_send(chat_id, "🤖 Invoice Bot\n\n🔒 Введите пароль:")
        return

    if text.startswith('/folder'):
        safe_send(chat_id, f"📁 Документы:\n{GOOGLE_DRIVE_FOLDER_URL}")
        return

    if text == '/new':
        if user_state.get(chat_id, {}).get('auth'):
            start_input(chat_id)
        else:
            user_state[chat_id] = {'auth': False}
            safe_send(chat_id, "🔒 Введите пароль:")
        return

    state = user_state.get(chat_id, {})

    # Auth
    if not state.get('auth'):
        if text == BOT_PASSWORD:
            user_state[chat_id] = {'auth': True}
            safe_send(chat_id, "✅ Доступ разрешён.\n\n📤 Отправьте PDF/фото или введите /new")
        else:
            safe_send(chat_id, "❌ Неверный пароль.")
        return

    if state.get('waiting_for') == 'bulk':
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) < 8:
            safe_send(chat_id, f"❌ Нужно 8 строк. Попробуйте ещё раз:\n\n{INPUT_TEMPLATE}")
            return

        data = parse_bulk(lines)
        if not data:
            safe_send(chat_id, "❌ Ошибка в данных. Проверьте числа (Amount, Fee).")
            return

        safe_send(chat_id, "📤 Отправляю...")
        if submit_to_google_form(data):
            send_completion(chat_id, data)
        else:
            safe_send(chat_id, "❌ Ошибка отправки в Google Form")

        user_state[chat_id] = {'auth': True}
    else:
        safe_send(chat_id, "📤 Отправьте PDF/фото или введите /new")


# ── Start ──────────────────────────────────────────────────────────────────────

print("📅 Started at:", datetime.now())

try:
    bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook cleared")
except Exception as e:
    print(f"⚠️ Webhook clear error: {e}")

print("Waiting 35s for old connections to expire...")
time.sleep(35)

while True:
    try:
        print("🔄 Bot polling started...")
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        print(f"❌ Bot error: {e}")
        time.sleep(5)
