import os
import telebot
from datetime import datetime
from telebot import types
import requests
import time
import threading

os.environ['PYTHONUNBUFFERED'] = '1'

print("🚀 Auto Invoice Bot starting...")

BOT_TOKEN = '8760516717:AAH6q12ZZZujNdW6XQh8aigZGVOO4fUSQwo'
bot = telebot.TeleBot(BOT_TOKEN)
user_state = {}

WEBAPP_URL = "https://script.google.com/macros/s/AKfycbx9j2J0RmxBZkR6kUHaLVw2L8DYsSj4Kyi-1zZp2P_sX3lZ0gfV_QCUxKEwcyTUGsYbDg/exec"
GOOGLE_DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1_MYLYCzkXrrG8FJzW8JazWHTXdS2sgC4"

VALID_BUYERS = ['169705', '657313', '218751', '218761']

REGULAR_CUSTOMER = {
    'name': 'ჰასანოვი მუქალდარ',
    'id': '28001088898'
}


def safe_send_message(chat_id, text, reply_markup=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            if reply_markup:
                return bot.send_message(chat_id, text, reply_markup=reply_markup)
            else:
                return bot.send_message(chat_id, text)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return None

def safe_answer_callback(call_id, text, max_retries=3):
    for attempt in range(max_retries):
        try:
            return bot.answer_callback_query(call_id, text)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return None

def ask_input_method(chat_id):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✏️ Ручной ввод", callback_data="input_manual"),
        types.InlineKeyboardButton("📄 Загрузка PDF", callback_data="input_pdf")
    )
    safe_send_message(chat_id, "Выберите способ ввода:", reply_markup=keyboard)

def ask_buyer_selection(chat_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for buyer_id in VALID_BUYERS:
        keyboard.add(types.InlineKeyboardButton(
            text=f"Buyer {buyer_id}",
            callback_data=f"buyer_{buyer_id}"
        ))
    safe_send_message(chat_id, "🏢 Выберите Buyer:", reply_markup=keyboard)
    user_state[chat_id]['waiting_for'] = 'buyer_selection'

def ask_customer_type(chat_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Постоянный", callback_data="customer_regular"),
        types.InlineKeyboardButton("🆕 Новый", callback_data="customer_new")
    )
    safe_send_message(chat_id, "👤 Выберите тип клиента:", reply_markup=keyboard)
    user_state[chat_id]['waiting_for'] = 'customer_type_selection'

def submit_to_google_form(data):
    try:
        form_data = {
            'year':         data.get('Date_Year', ''),
            'month':        data.get('Date_Month', ''),
            'day':          data.get('Date_Day', ''),
            'customer_name': data.get('Customer_Name', ''),
            'customer_id':  data.get('Customer_ID', ''),
            'buyer':        data.get('Buyer', ''),
            'lot':          data.get('Lot', ''),
            'vehicle':      data.get('Vehicle', ''),
            'vin':          data.get('Vin', ''),
            'amount_usd':   data.get('Amount_USD', ''),
            'auction_fee':  data.get('Auction_Fee', ''),
            'total_usd':    data.get('Total_USD', ''),
        }

        response = requests.post(
            WEBAPP_URL,
            data=form_data,
            timeout=30
        )
        print(f"Sheets response: {response.status_code} {response.text}")
        result = response.json()
        if result.get('ok'):
            return True, 'OK'
        else:
            return False, result.get('error', 'unknown error')
    except Exception as e:
        print(f"Submit error: {e}")
        return False, str(e)

def send_completion_message(chat_id, data):
    try:
        summary = "✅ Отправлено\n\n"
        summary += f"📅 {data['Date_Day']}.{data['Date_Month']}.{data['Date_Year']}\n"
        summary += f"👤 {data.get('Customer_Name', 'N/A')} (ID: {data.get('Customer_ID', 'N/A')})\n"
        summary += f"🏢 Buyer: {data.get('Buyer', 'N/A')}\n"
        summary += f"🚗 Lot: {data.get('Lot', 'N/A')}\n"
        summary += f"🚙 {data.get('Vehicle', 'N/A')}\n"
        summary += f"🔢 VIN: {data.get('Vin', 'N/A')}\n"
        summary += f"💰 Amount: ${data.get('Amount_USD', 'N/A')}\n"
        summary += f"💸 Fee: ${data.get('Auction_Fee', 'N/A')}\n"
        summary += f"💵 Total: ${data.get('Total_USD', 'N/A')}\n"

        safe_send_message(chat_id, summary)
        time.sleep(1)
        safe_send_message(chat_id, f"📁 Документы (1-3 мин):\n{GOOGLE_DRIVE_FOLDER_URL}")
        time.sleep(1)
        ask_input_method(chat_id)

        def send_reminder():
            time.sleep(120)
            safe_send_message(chat_id, f"⏰ Проверьте документы:\n{GOOGLE_DRIVE_FOLDER_URL}")

        threading.Thread(target=send_reminder, daemon=True).start()

    except Exception as e:
        safe_send_message(chat_id, "❌ Ошибка")

# ── Callback handlers ──────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: call.data in ['input_manual', 'input_pdf'])
def handle_input_method(call):
    try:
        chat_id = call.message.chat.id
        if call.data == 'input_manual':
            now = datetime.now()
            user_state[chat_id] = {
                'data': {
                    'Date_Year': str(now.year),
                    'Date_Month': str(now.month),
                    'Date_Day': str(now.day)
                },
                'waiting_for': 'Lot'
            }
            safe_answer_callback(call.id, "Ручной ввод")
            safe_send_message(chat_id, "🚗 Введите LOT:")
        else:
            safe_answer_callback(call.id, "Загрузка PDF")
            safe_send_message(chat_id, "📤 Отправьте PDF или фото инвойса")
    except Exception as e:
        safe_answer_callback(call.id, "Ошибка")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buyer_'))
def handle_buyer_selection(call):
    try:
        chat_id = call.message.chat.id
        buyer_id = call.data.split('_')[1]

        if chat_id in user_state and user_state[chat_id].get('waiting_for') == 'buyer_selection':
            user_state[chat_id]['data']['Buyer'] = buyer_id

            safe_answer_callback(call.id, f"Выбран {buyer_id}")
            safe_send_message(chat_id, f"✅ Buyer: {buyer_id}")

            time.sleep(1)
            ask_customer_type(chat_id)
    except Exception as e:
        safe_answer_callback(call.id, "Ошибка")

@bot.callback_query_handler(func=lambda call: call.data in ['customer_regular', 'customer_new'])
def handle_customer_type_selection(call):
    try:
        chat_id = call.message.chat.id

        if chat_id in user_state and user_state[chat_id].get('waiting_for') == 'customer_type_selection':
            if call.data == 'customer_regular':
                user_state[chat_id]['data']['Customer_Name'] = REGULAR_CUSTOMER['name']
                user_state[chat_id]['data']['Customer_ID'] = REGULAR_CUSTOMER['id']

                safe_answer_callback(call.id, "Постоянный клиент")
                safe_send_message(chat_id, f"✅ Customer: {REGULAR_CUSTOMER['name']}")
                time.sleep(1)
                safe_send_message(chat_id, f"✅ ID: {REGULAR_CUSTOMER['id']}")
                time.sleep(1)
                safe_send_message(chat_id, "💸 Введите Auction Fee:")
                user_state[chat_id]['waiting_for'] = 'Auction_Fee'

            else:
                safe_answer_callback(call.id, "Новый клиент")
                safe_send_message(chat_id, "👤 Введите Customer Name:")
                user_state[chat_id]['waiting_for'] = 'Customer_Name'
    except Exception as e:
        safe_answer_callback(call.id, "Ошибка")

# ── File handler ───────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['document', 'photo'])
def handle_file(message):
    chat_id = message.chat.id

    now = datetime.now()
    user_state[chat_id] = {
        'data': {
            'Date_Year': str(now.year),
            'Date_Month': str(now.month),
            'Date_Day': str(now.day)
        },
        'waiting_for': 'Lot'
    }

    safe_send_message(chat_id, "✅ Инвойс получен. Вводим данные вручную.\n\n🚗 Введите LOT:")

# ── Text input handler ─────────────────────────────────────────────────────────

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if text.startswith('/start'):
        ask_input_method(chat_id)
        return
    if text.startswith('/folder'):
        safe_send_message(chat_id, f"📁 Документы:\n{GOOGLE_DRIVE_FOLDER_URL}")
        return

    if chat_id not in user_state:
        ask_input_method(chat_id)
        return

    waiting = user_state[chat_id].get('waiting_for')

    if waiting == 'Lot':
        user_state[chat_id]['data']['Lot'] = text
        safe_send_message(chat_id, f"✅ LOT: {text}\n\n🔢 Введите VIN (17 символов):")
        user_state[chat_id]['waiting_for'] = 'Vin'

    elif waiting == 'Vin':
        user_state[chat_id]['data']['Vin'] = text
        safe_send_message(chat_id, f"✅ VIN: {text}\n\n🚙 Введите автомобиль (например: 2021 NISSAN KICKS S WHITE):")
        user_state[chat_id]['waiting_for'] = 'Vehicle'

    elif waiting == 'Vehicle':
        user_state[chat_id]['data']['Vehicle'] = text
        safe_send_message(chat_id, f"✅ Автомобиль: {text}\n\n💰 Введите Amount USD (только цифры, например: 5680.00):")
        user_state[chat_id]['waiting_for'] = 'Amount_USD'

    elif waiting == 'Amount_USD':
        user_state[chat_id]['data']['Amount_USD'] = text
        safe_send_message(chat_id, f"✅ Amount USD: {text}")
        time.sleep(1)
        ask_buyer_selection(chat_id)

    elif waiting == 'Customer_Name':
        user_state[chat_id]['data']['Customer_Name'] = text
        safe_send_message(chat_id, f"✅ Customer: {text}\n\n🆔 Введите Customer ID:")
        user_state[chat_id]['waiting_for'] = 'Customer_ID'

    elif waiting == 'Customer_ID':
        user_state[chat_id]['data']['Customer_ID'] = text
        safe_send_message(chat_id, f"✅ ID: {text}\n\n💸 Введите Auction Fee:")
        user_state[chat_id]['waiting_for'] = 'Auction_Fee'

    elif waiting == 'Auction_Fee':
        try:
            fee = float(text.replace(',', '').replace(' ', ''))
            amount_raw = user_state[chat_id]['data'].get('Amount_USD', '0')
            amount = float(amount_raw.replace(',', '').replace('$', '').replace(' ', ''))
            total = round(amount + fee, 2)

            user_state[chat_id]['data']['Auction_Fee'] = str(fee)
            user_state[chat_id]['data']['Total_USD'] = str(total)

            safe_send_message(chat_id, f"✅ Auction Fee: {fee}\n💵 Total USD: {total}\n\n📤 Отправляю...")

            success, detail = submit_to_google_form(user_state[chat_id]['data'])
            if success:
                send_completion_message(chat_id, user_state[chat_id]['data'])
            else:
                safe_send_message(chat_id, f"❌ Ошибка отправки в Google Form:\n{detail}")
                ask_input_method(chat_id)

            user_state.pop(chat_id, None)

        except ValueError:
            safe_send_message(chat_id, "❌ Введите число, например: 625.00")

# ── Start bot ──────────────────────────────────────────────────────────────────

print("📅 Started at:", datetime.now())

try:
    bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook cleared")
except Exception as e:
    print(f"⚠️ Webhook clear error: {e}")

time.sleep(2)

while True:
    try:
        print("🔄 Bot polling started...")
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        print(f"❌ Bot error: {e}")
        print("🔄 Restarting in 5 seconds...")
        time.sleep(5)
