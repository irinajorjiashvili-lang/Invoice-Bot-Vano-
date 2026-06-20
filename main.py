import os
import re
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

GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLSdF6sBVKX0dW4qFcsmcn1_cBceoOY_wg-AvKFWFfdU0KSv6Yw/viewform"
GOOGLE_FORM_URL  = "https://docs.google.com/forms/d/e/1FAIpQLSdF6sBVKX0dW4qFcsmcn1_cBceoOY_wg-AvKFWFfdU0KSv6Yw/formResponse"
DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1_MYLYCzkXrrG8FJzW8JazWHTXdS2sgC4"

FORM_FIELDS = {
    'Date_Year':     'entry.2136135204_year',
    'Date_Month':    'entry.2136135204_month',
    'Date_Day':      'entry.2136135204_day',
    'Lot':           'entry.1163357354',
    'Vin':           'entry.1094744061',
    'Vehicle':       'entry.341377459',
    'Amount_USD':    'entry.1342000086',
    'Buyer':         'entry.784567376',
    'Customer_Name': 'entry.21018057',
    'Customer_ID':   'entry.1116307930',
    'Auction_Fee':   'entry.532543637',
    'Total_USD':     'entry.857168306',
}

BULK_TEMPLATE = (
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

bot        = telebot.TeleBot(BOT_TOKEN)
user_state = {}


def safe_send(chat_id, text, markup=None, parse_mode=None):
    for i in range(3):
        try:
            return bot.send_message(chat_id, text, reply_markup=markup, parse_mode=parse_mode)
        except Exception:
            if i < 2:
                time.sleep(1)
    return None

def safe_cb(call_id, text=''):
    for i in range(3):
        try:
            return bot.answer_callback_query(call_id, text)
        except Exception:
            if i < 2:
                time.sleep(1)

def submit_form(data):
    try:
        session = requests.Session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        session.headers.update(headers)

        # Загружаем форму чтобы получить fbzx токен и куки
        view = session.get(GOOGLE_FORM_VIEW, timeout=15)
        fbzx_match = re.search(r'[\"\']fbzx[\"\']\s*[,:]\s*[\"\']?(-?\d+)', view.text)
        fbzx = fbzx_match.group(1) if fbzx_match else str(int(time.time() * 1000))
        print(f"[FORM] fbzx={fbzx}")

        form_data = {v: str(data[k]) for k, v in FORM_FIELDS.items() if k in data and data[k]}
        form_data['fvv']         = '1'
        form_data['fbzx']        = fbzx
        form_data['pageHistory'] = '0'

        r = session.post(GOOGLE_FORM_URL, data=form_data, allow_redirects=True, timeout=30)
        print(f"[FORM] {r.status_code}")
        return r.status_code in [200, 302]
    except Exception as e:
        print(f"[FORM] {e}")
        return False

def parse_bulk(text):
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if len(lines) < 8:
        return None
    try:
        now    = datetime.now()
        amount = float(lines[3].replace(',', '').replace('$', '').replace(' ', ''))
        fee    = float(lines[7].replace(',', '').replace(' ', ''))
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

def summary_text(d):
    return (
        "📋 <b>Проверьте данные:</b>\n\n"
        f"📅 {d['Date_Day']}.{d['Date_Month']}.{d['Date_Year']}\n"
        f"🚗 Лот: <b>{d['Lot']}</b>\n"
        f"🔢 VIN: {d['Vin']}\n"
        f"🚙 Авто: {d['Vehicle']}\n"
        f"🏢 Buyer: {d['Buyer']}\n"
        f"👤 {d['Customer_Name']} ({d['Customer_ID']})\n"
        f"💰 Amount: ${d['Amount_USD']}\n"
        f"💸 Fee: ${d['Auction_Fee']}\n"
        f"💵 Total: ${d['Total_USD']}"
    )

def confirm_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
        types.InlineKeyboardButton("❌ Отмена",      callback_data="cancel"),
    )
    return kb

def new_invoice_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📋 Новый инвойс", callback_data="new_inv"))
    return kb

def do_submit(chat_id, data):
    if submit_form(data):
        safe_send(chat_id,
            f"✅ Отправлено!\n\n📁 Документы (1-3 мин):\n{DRIVE_FOLDER_URL}",
            markup=new_invoice_kb()
        )
        def reminder():
            time.sleep(120)
            safe_send(chat_id,
                f"⏰ Проверьте документы:\n{DRIVE_FOLDER_URL}",
                markup=new_invoice_kb()
            )
        threading.Thread(target=reminder, daemon=True).start()
    else:
        safe_send(chat_id, "❌ Ошибка отправки. Попробуйте /new", markup=new_invoice_kb())
    user_state[chat_id] = {'auth': True}


# ── Callbacks ──────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == 'confirm')
def cb_confirm(call):
    chat_id = call.message.chat.id
    data = user_state.get(chat_id, {}).get('data')
    if not data:
        return safe_cb(call.id)
    safe_cb(call.id, "Отправляю...")
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    do_submit(chat_id, data)

@bot.callback_query_handler(func=lambda c: c.data == 'cancel')
def cb_cancel(call):
    chat_id = call.message.chat.id
    safe_cb(call.id, "Отменено")
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    user_state[chat_id] = {'auth': True, 'waiting_for': 'bulk_input'}
    safe_send(chat_id, f"❌ Отменено. Введите данные заново:\n\n{BULK_TEMPLATE}")

@bot.callback_query_handler(func=lambda c: c.data == 'new_inv')
def cb_new(call):
    chat_id = call.message.chat.id
    safe_cb(call.id)
    user_state[chat_id] = {'auth': True, 'waiting_for': 'bulk_input'}
    safe_send(chat_id, BULK_TEMPLATE)


# ── Message handlers ───────────────────────────────────────────────────────────

@bot.message_handler(content_types=['document', 'photo'])
def on_file(message):
    chat_id = message.chat.id
    if not user_state.get(chat_id, {}).get('auth'):
        user_state[chat_id] = {'auth': False}
        return safe_send(chat_id, "🔒 Введите пароль:")
    user_state[chat_id] = {'auth': True, 'waiting_for': 'bulk_input'}
    safe_send(chat_id, f"✅ Файл получен.\n\n{BULK_TEMPLATE}")

@bot.message_handler(content_types=['text'])
def on_text(message):
    chat_id = message.chat.id
    text    = message.text.strip()

    if text == '/start':
        user_state[chat_id] = {'auth': False}
        return safe_send(chat_id, "🤖 Invoice Bot\n\n🔒 Введите пароль:")

    state = user_state.get(chat_id, {})

    if not state.get('auth'):
        if text == BOT_PASSWORD:
            user_state[chat_id] = {'auth': True}
            safe_send(chat_id, "✅ Доступ разрешён.\n\n📤 Отправьте PDF/фото или введите /new")
        else:
            safe_send(chat_id, "❌ Неверный пароль.")
        return

    if text == '/new':
        user_state[chat_id] = {'auth': True, 'waiting_for': 'bulk_input'}
        return safe_send(chat_id, BULK_TEMPLATE)

    waiting = state.get('waiting_for')

    if waiting == 'bulk_input':
        data = parse_bulk(text)
        if not data:
            return safe_send(chat_id, f"❌ Нужно 8 строк. Попробуйте ещё раз:\n\n{BULK_TEMPLATE}")
        state['data']        = data
        state['waiting_for'] = 'confirm'
        safe_send(chat_id, summary_text(data), markup=confirm_kb(), parse_mode='HTML')
    else:
        safe_send(chat_id, "📤 Отправьте PDF/фото или введите /new")


# ── Start ──────────────────────────────────────────────────────────────────────

print(f"Started at: {datetime.now()}")
try:
    bot.delete_webhook(drop_pending_updates=True)
    print("Webhook cleared")
except Exception as e:
    print(f"Webhook error: {e}")

print("Waiting 35s...")
time.sleep(35)

while True:
    try:
        print("Bot polling started...")
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        print(f"Bot error: {e}")
        time.sleep(5)
