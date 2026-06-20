import os
import re
import telebot
from datetime import datetime
from telebot import types
import requests
import time
import threading

os.environ['PYTHONUNBUFFERED'] = '1'
print("🚀 Auto Invoice Bot starting...")

BOT_TOKEN  = os.environ.get('BOT_TOKEN', '8760516717:AAEmEESz8YxnqEnBIOrHKk5-n8Hns5L8wVA')
BOT_PASSWORD = os.environ.get('BOT_PASSWORD', 'Hybridi2026')
bot = telebot.TeleBot(BOT_TOKEN)
user_state = {}

GOOGLE_FORM_VIEW_URL   = "https://docs.google.com/forms/d/e/1FAIpQLSdF6sBVKX0dW4qFcsmcn1_cBceoOY_wg-AvKFWFfdU0KSv6Yw/viewform"
GOOGLE_FORM_SUBMIT_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdF6sBVKX0dW4qFcsmcn1_cBceoOY_wg-AvKFWFfdU0KSv6Yw/formResponse"
GOOGLE_DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1_MYLYCzkXrrG8FJzW8JazWHTXdS2sgC4"

GOOGLE_FORM_FIELDS = {
    'Date':          'entry.2136135204',
    'Customer_Name': 'entry.21018057',
    'Customer_ID':   'entry.1116307930',
    'Lot':           'entry.1163357354',
    'Vehicle':       'entry.341377459',
    'Vin':           'entry.1094744061',
    'Amount_USD':    'entry.1342000086',
    'Auction_Fee':   'entry.532543637',
    'Total_USD':     'entry.857168306',
    'Buyer':         'entry.784567376',
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
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
        })

        # Получаем страницу формы — нужны куки и fbzx токен
        page = session.get(GOOGLE_FORM_VIEW_URL, timeout=15)
        fbzx = re.search(r'"fbzx"\s*:\s*"?(-?\d+)"?', page.text)
        fbzx = fbzx.group(1) if fbzx else str(int(time.time() * 1000))
        print(f"[FORM] fbzx={fbzx}")

        form_data = {}
        for field, entry_id in GOOGLE_FORM_FIELDS.items():
            if field in data and data[field]:
                form_data[entry_id] = str(data[field])

        form_data['fvv']         = '1'
        form_data['fbzx']        = fbzx
        form_data['pageHistory'] = '0'

        response = session.post(
            GOOGLE_FORM_SUBMIT_URL,
            data=form_data,
            headers={'Referer': GOOGLE_FORM_VIEW_URL},
            allow_redirects=True,
            timeout=30
        )
        print(f"[FORM] status={response.status_code}")
        return response.status_code in [200, 302]
    except Exception as e:
        print(f"[FORM] error: {e}")
        return False


def send_completion(chat_id, data):
    msg = (
        "✅ Отправлено\n\n"
        f"📅 {data['Date']}\n"
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
        return {
            'Date':          datetime.now().strftime('%Y-%m-%d'),
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
