import os
import time
import threading
import requests
import telebot
from datetime import datetime
from telebot import types

os.environ['PYTHONUNBUFFERED'] = '1'

print("Starting Invoice Bot...")

BOT_TOKEN    = os.environ.get('BOT_TOKEN', '8760516717:AAEmEESz8YxnqEnBIOrHKk5-n8Hns5L8wVA')
BOT_PASSWORD = os.environ.get('BOT_PASSWORD', 'Hybridi2026')

GOOGLE_FORM_URL  = "https://docs.google.com/forms/u/0/d/1wOP-nAS7h8y8r4L6ezeaNow2v9XVGkQ3mOamzX-dLKA/formResponse"
DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1_MYLYCzkXrrG8FJzW8JazWHTXdS2sgC4"

FORM_FIELDS = {
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
    'Buyer':         'entry.784567376',
}

VALID_BUYERS     = ['169705', '657313', '218751', '218761']
REGULAR_CUSTOMER = {'name': 'ჰასანოვი მუქალდარ', 'id': '28001088898'}

bot        = telebot.TeleBot(BOT_TOKEN)
user_state = {}


def safe_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    for attempt in range(3):
        try:
            return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def safe_answer_callback(call_id, text=''):
    for attempt in range(3):
        try:
            return bot.answer_callback_query(call_id, text)
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def submit_to_google_form(data):
    try:
        form_data = {}
        for field, entry_id in FORM_FIELDS.items():
            if field in data and data[field]:
                form_data[entry_id] = str(data[field])

        response = requests.post(
            GOOGLE_FORM_URL,
            data=form_data,
            headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'},
            allow_redirects=True,
            timeout=30,
        )
        print(f"[FORM] Status: {response.status_code}")
        return response.status_code in [200, 302, 400]
    except Exception as e:
        print(f"[FORM] Error: {e}")
        return False


def send_completion_message(chat_id, data):
    summary = (
        "✅ Отправлено\n\n"
        f"📅 {data['Date_Day']}.{data['Date_Month']}.{data['Date_Year']}\n"
        f"👤 {data.get('Customer_Name', '—')} (ID: {data.get('Customer_ID', '—')})\n"
        f"🏢 Buyer: {data.get('Buyer', '—')}\n"
        f"🚗 Lot: {data.get('Lot', '—')}\n"
        f"🚙 {data.get('Vehicle', '—')}\n"
        f"🔢 VIN: {data.get('Vin', '—')}\n"
        f"💰 Amount: ${data.get('Amount_USD', '—')}\n"
        f"💸 Fee: ${data.get('Auction_Fee', '—')}\n"
        f"💵 Total: ${data.get('Total_USD', '—')}\n\n"
        f"📁 Документы (1-3 мин):\n{DRIVE_FOLDER_URL}"
    )
    safe_send_message(chat_id, summary)

    def send_reminder():
        time.sleep(120)
        safe_send_message(chat_id, f"⏰ Проверьте документы:\n{DRIVE_FOLDER_URL}")

    threading.Thread(target=send_reminder, daemon=True).start()


def ask_buyer(chat_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    for b in VALID_BUYERS:
        kb.add(types.InlineKeyboardButton(f"Buyer {b}", callback_data=f"buyer_{b}"))
    safe_send_message(chat_id, "🏢 Выберите Buyer:", reply_markup=kb)
    user_state[chat_id]['waiting_for'] = 'buyer_selection'


def ask_customer_type(chat_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔄 Постоянный", callback_data="customer_regular"),
        types.InlineKeyboardButton("🆕 Новый",      callback_data="customer_new"),
    )
    safe_send_message(chat_id, "👤 Тип клиента:", reply_markup=kb)
    user_state[chat_id]['waiting_for'] = 'customer_type'


# ── Callbacks ──────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data.startswith('buyer_'))
def on_buyer(call):
    chat_id  = call.message.chat.id
    buyer_id = call.data.split('_')[1]
    if chat_id not in user_state or user_state[chat_id].get('waiting_for') != 'buyer_selection':
        return safe_answer_callback(call.id)
    user_state[chat_id]['data']['Buyer'] = buyer_id
    safe_answer_callback(call.id, f"Выбран {buyer_id}")
    safe_send_message(chat_id, f"✅ Buyer: {buyer_id}")
    time.sleep(0.5)
    ask_customer_type(chat_id)


@bot.callback_query_handler(func=lambda c: c.data in ['customer_regular', 'customer_new'])
def on_customer_type(call):
    chat_id = call.message.chat.id
    if chat_id not in user_state or user_state[chat_id].get('waiting_for') != 'customer_type':
        return safe_answer_callback(call.id)

    if call.data == 'customer_regular':
        user_state[chat_id]['data']['Customer_Name'] = REGULAR_CUSTOMER['name']
        user_state[chat_id]['data']['Customer_ID']   = REGULAR_CUSTOMER['id']
        safe_answer_callback(call.id, "Постоянный клиент")
        safe_send_message(chat_id, f"✅ {REGULAR_CUSTOMER['name']} / {REGULAR_CUSTOMER['id']}")
        time.sleep(0.5)
        safe_send_message(chat_id, "💸 Введите Auction Fee:")
        user_state[chat_id]['waiting_for'] = 'Auction_Fee'
    else:
        safe_answer_callback(call.id, "Новый клиент")
        safe_send_message(chat_id, "👤 Введите Customer Name:")
        user_state[chat_id]['waiting_for'] = 'Customer_Name'


# ── Message handlers ───────────────────────────────────────────────────────────

@bot.message_handler(content_types=['document', 'photo'])
def on_file(message):
    chat_id = message.chat.id
    state   = user_state.get(chat_id, {})

    if not state.get('auth'):
        safe_send_message(chat_id, "🔒 Введите пароль:")
        user_state[chat_id] = {'auth': False}
        return

    now = datetime.now()
    user_state[chat_id] = {
        'auth': True,
        'data': {'Date_Year': str(now.year), 'Date_Month': str(now.month), 'Date_Day': str(now.day)},
        'waiting_for': 'Lot',
    }
    safe_send_message(chat_id, "✅ Инвойс получен.\n\n🚗 Введите LOT:")


@bot.message_handler(content_types=['text'])
def on_text(message):
    chat_id = message.chat.id
    text    = message.text.strip()

    if text == '/start':
        user_state.pop(chat_id, None)
        safe_send_message(chat_id, "🤖 Invoice Bot\n\n🔒 Введите пароль:")
        user_state[chat_id] = {'auth': False}
        return

    if text == '/folder':
        safe_send_message(chat_id, f"📁 Документы:\n{DRIVE_FOLDER_URL}")
        return

    state = user_state.get(chat_id, {})

    if not state.get('auth'):
        if text == BOT_PASSWORD:
            user_state[chat_id] = {'auth': True}
            safe_send_message(chat_id, "✅ Доступ разрешён.\n\n📤 Отправьте PDF или фото инвойса.")
        else:
            safe_send_message(chat_id, "❌ Неверный пароль.")
        return

    waiting = state.get('waiting_for')

    if not waiting:
        safe_send_message(chat_id, "📤 Отправьте PDF или фото инвойса.")
        return

    if waiting == 'Lot':
        state['data']['Lot'] = text
        safe_send_message(chat_id, f"✅ LOT: {text}\n\n🔢 Введите VIN:")
        state['waiting_for'] = 'Vin'

    elif waiting == 'Vin':
        state['data']['Vin'] = text
        safe_send_message(chat_id, f"✅ VIN: {text}\n\n🚙 Введите автомобиль (напр: 2021 NISSAN KICKS S WHITE):")
        state['waiting_for'] = 'Vehicle'

    elif waiting == 'Vehicle':
        state['data']['Vehicle'] = text
        safe_send_message(chat_id, f"✅ Авто: {text}\n\n💰 Введите Amount USD:")
        state['waiting_for'] = 'Amount_USD'

    elif waiting == 'Amount_USD':
        state['data']['Amount_USD'] = text
        safe_send_message(chat_id, f"✅ Amount: {text}")
        time.sleep(0.5)
        ask_buyer(chat_id)

    elif waiting == 'Customer_Name':
        state['data']['Customer_Name'] = text
        safe_send_message(chat_id, f"✅ Customer: {text}\n\n🆔 Введите Customer ID:")
        state['waiting_for'] = 'Customer_ID'

    elif waiting == 'Customer_ID':
        state['data']['Customer_ID'] = text
        safe_send_message(chat_id, f"✅ ID: {text}\n\n💸 Введите Auction Fee:")
        state['waiting_for'] = 'Auction_Fee'

    elif waiting == 'Auction_Fee':
        try:
            fee    = float(text.replace(',', '').replace(' ', ''))
            amount = float(state['data'].get('Amount_USD', '0').replace(',', '').replace('$', '').replace(' ', ''))
            total  = round(amount + fee, 2)

            state['data']['Auction_Fee'] = str(fee)
            state['data']['Total_USD']   = str(total)

            safe_send_message(chat_id, f"✅ Fee: {fee}\n💵 Total: {total}\n\n📤 Отправляю...")

            if submit_to_google_form(state['data']):
                send_completion_message(chat_id, state['data'])
            else:
                safe_send_message(chat_id, "❌ Ошибка отправки в Google Form")

            user_state[chat_id] = {'auth': True}

        except ValueError:
            safe_send_message(chat_id, "❌ Введите число, например: 625.00")


# ── Start ──────────────────────────────────────────────────────────────────────

print(f"Started at: {datetime.now()}")

try:
    bot.delete_webhook(drop_pending_updates=True)
    print("Webhook cleared")
except Exception as e:
    print(f"Webhook error: {e}")

print("Waiting 35s for old connections to expire...")
time.sleep(35)

while True:
    try:
        print("Bot polling started...")
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        print(f"Bot error: {e}")
        time.sleep(5)
