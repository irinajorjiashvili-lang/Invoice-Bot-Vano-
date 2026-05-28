import os
import csv
import io
import re
import telebot
from datetime import datetime
from telebot import types
import requests
import time
import threading

os.environ['PYTHONUNBUFFERED'] = '1'

print("🚀 Auto Invoice Bot starting...")

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8760516717:AAFjIvQTVgWIM2wJQVlRBEped4rM6fAakLM')
bot = telebot.TeleBot(BOT_TOKEN)
user_state = {}

GOOGLE_FORM_SUBMIT_URL = "https://docs.google.com/forms/u/0/d/1wOP-nAS7h8y8r4L6ezeaNow2v9XVGkQ3mOamzX-dLKA/formResponse"
SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/19UUm74QdfeZtFsQoTf-X77h7brpIQ9_hAS0GreNidoQ/export?format=csv&gid=1152025982"

VALID_BUYERS = ['169705', '657313', '218751', '218761']

REGULAR_CUSTOMER = {
    'name': 'ჰასანოვი მუქალდარ',
    'id': '28001088898'
}

GOOGLE_FORM_FIELDS = {
    'Date_Year': 'entry.2136135204_year',
    'Date_Month': 'entry.2136135204_month',
    'Date_Day': 'entry.2136135204_day',
    'Customer_Name': 'entry.21018057',
    'Customer_ID': 'entry.1116307930',
    'Lot': 'entry.1163357354',
    'Vehicle': 'entry.341377459',
    'Vin': 'entry.1094744061',
    'Amount_USD': 'entry.1342000086',
    'Auction_Fee': 'entry.532543637',
    'Total_USD': 'entry.857168306',
    'Buyer': 'entry.784567376'
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def safe_send_message(chat_id, text, reply_markup=None, parse_mode=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
    return None

def safe_answer_callback(call_id, text, max_retries=3):
    for attempt in range(max_retries):
        try:
            return bot.answer_callback_query(call_id, text)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
    return None

# ── Google Sheets ──────────────────────────────────────────────────────────────

def fetch_invoices():
    try:
        response = requests.get(SHEETS_CSV_URL, allow_redirects=True, timeout=30)
        content = response.content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)
    except Exception:
        return []

def get_doc_types_from_row(row):
    """Returns list of (name, url) for all documents in a row"""
    doc_types = []
    keys = list(row.keys())
    for i, key in enumerate(keys):
        value = (row[key] or '').strip()
        if not (value.startswith('https://drive.google.com/file/d/') or
                value.startswith('https://docs.google.com/document/d/')):
            continue
        # Document name is in the next column
        name = None
        if i + 1 < len(keys):
            next_val = (row[keys[i + 1]] or '').strip()
            if (next_val and not next_val.startswith('http')
                    and 'Document successfully' not in next_val
                    and 'Starting at' not in next_val
                    and len(next_val) < 80):
                name = next_val
        if not name:
            name = f"Документ {len(doc_types) + 1}"
        doc_types.append((name, value))
    return doc_types

# ── Google Drive download ──────────────────────────────────────────────────────

def download_drive_file(url):
    """Download file from Google Drive. Returns bytes or None."""
    try:
        file_id = None
        is_doc = False

        if '/file/d/' in url:
            file_id = url.split('/file/d/')[1].split('/')[0].split('?')[0]
        elif '/document/d/' in url:
            file_id = url.split('/document/d/')[1].split('/')[0].split('?')[0]
            is_doc = True

        if not file_id:
            return None

        if is_doc:
            dl_url = f"https://docs.google.com/document/d/{file_id}/export?format=pdf"
        else:
            dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        session = requests.Session()
        resp = session.get(dl_url, allow_redirects=True, timeout=60)

        # Handle large file virus-scan confirmation
        if resp.status_code == 200 and b'<!DOCTYPE' in resp.content[:100]:
            match = re.search(rb'confirm=([0-9A-Za-z_-]+)', resp.content)
            if match:
                confirm = match.group(1).decode()
                resp = session.get(f"{dl_url}&confirm={confirm}", allow_redirects=True, timeout=60)

        if resp.status_code == 200 and len(resp.content) > 1000:
            return resp.content
        return None
    except Exception:
        return None

def send_pdf_to_user(chat_id, name, url):
    """Download PDF and send to user. Falls back to link if download fails."""
    safe_send_message(chat_id, f"⬇️ Загружаю: <b>{name}</b>...", parse_mode='HTML')
    content = download_drive_file(url)
    if content:
        try:
            file_obj = io.BytesIO(content)
            file_obj.name = f"{name}.pdf"
            bot.send_document(chat_id, file_obj, caption=name)
            return
        except Exception:
            pass
    # Fallback: send link
    safe_send_message(chat_id, f"📎 <b>{name}</b>\n{url}", parse_mode='HTML')

# ── Document type selector ─────────────────────────────────────────────────────

def show_doc_type_selector(chat_id, lot, doc_types):
    """Show inline buttons for selecting document types"""
    if not doc_types:
        safe_send_message(chat_id, f"❌ Документы для лота <b>{lot}</b> не найдены", parse_mode='HTML')
        return

    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id][f'doctypes_{lot}'] = doc_types
    user_state[chat_id][f'docsel_{lot}'] = set()

    keyboard = build_doctype_keyboard(lot, doc_types, set())
    safe_send_message(
        chat_id,
        f"📄 Документы для лота <b>{lot}</b>:\nВыберите нужные:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

def build_doctype_keyboard(lot, doc_types, selected):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for i, (name, url) in enumerate(doc_types):
        check = '☑' if i in selected else '☐'
        short_name = name[:40]
        keyboard.add(types.InlineKeyboardButton(
            text=f"{check} {short_name}",
            callback_data=f"dt_{lot}_{i}"
        ))
    keyboard.add(types.InlineKeyboardButton(
        text=f"📤 Отправить выбранные ({len(selected)})",
        callback_data=f"dtsend_{lot}"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="📂 Отправить все",
        callback_data=f"dtall_{lot}"
    ))
    return keyboard

@bot.callback_query_handler(func=lambda call: call.data.startswith('dt_') and not call.data.startswith('dtsend_') and not call.data.startswith('dtall_'))
def handle_doctype_toggle(call):
    chat_id = call.message.chat.id
    parts = call.data.split('_', 2)
    lot = parts[1]
    idx = int(parts[2])

    doc_types = user_state.get(chat_id, {}).get(f'doctypes_{lot}', [])
    selected = user_state.get(chat_id, {}).get(f'docsel_{lot}', set())

    if idx in selected:
        selected.discard(idx)
        safe_answer_callback(call.id, "Снято")
    else:
        selected.add(idx)
        safe_answer_callback(call.id, "Выбрано ✓")

    user_state[chat_id][f'docsel_{lot}'] = selected
    keyboard = build_doctype_keyboard(lot, doc_types, selected)
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=keyboard)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('dtsend_'))
def handle_doctype_send(call):
    chat_id = call.message.chat.id
    lot = call.data[len('dtsend_'):]
    safe_answer_callback(call.id, "Отправляю...")

    doc_types = user_state.get(chat_id, {}).get(f'doctypes_{lot}', [])
    selected = user_state.get(chat_id, {}).get(f'docsel_{lot}', set())

    if not selected:
        safe_send_message(chat_id, "❌ Ничего не выбрано")
        return

    for i in sorted(selected):
        if i < len(doc_types):
            name, url = doc_types[i]
            send_pdf_to_user(chat_id, name, url)
            time.sleep(0.5)

    user_state[chat_id][f'docsel_{lot}'] = set()

@bot.callback_query_handler(func=lambda call: call.data.startswith('dtall_'))
def handle_doctype_all(call):
    chat_id = call.message.chat.id
    lot = call.data[len('dtall_'):]
    safe_answer_callback(call.id, "Отправляю все...")

    doc_types = user_state.get(chat_id, {}).get(f'doctypes_{lot}', [])
    if not doc_types:
        safe_send_message(chat_id, "❌ Документы не найдены")
        return

    for name, url in doc_types:
        send_pdf_to_user(chat_id, name, url)
        time.sleep(0.5)

# ── Buyer & customer ───────────────────────────────────────────────────────────

def ask_buyer_selection(chat_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(text=b, callback_data=f"buyer_{b}") for b in VALID_BUYERS]
    keyboard.add(*buttons)
    keyboard.add(types.InlineKeyboardButton(text="✏️ Другой номер", callback_data="buyer_other"))
    safe_send_message(chat_id, "🏢 Выберите Buyer:", reply_markup=keyboard)
    user_state[chat_id]['waiting_for'] = 'buyer_selection'

def ask_customer_type(chat_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Постоянный", callback_data="customer_regular"),
        types.InlineKeyboardButton("🆕 Новый", callback_data="customer_new")
    )
    safe_send_message(chat_id, "👤 Тип клиента:", reply_markup=keyboard)
    user_state[chat_id]['waiting_for'] = 'customer_type_selection'

# ── Google Form ────────────────────────────────────────────────────────────────

def submit_to_google_form(data):
    try:
        form_data = {
            entry_id: str(data[field])
            for field, entry_id in GOOGLE_FORM_FIELDS.items()
            if field in data and data[field]
        }
        response = requests.post(
            GOOGLE_FORM_SUBMIT_URL,
            data=form_data,
            headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'},
            allow_redirects=True,
            timeout=30
        )
        return response.status_code in [200, 302, 400]
    except Exception:
        return False

def send_completion_message(chat_id, data):
    try:
        d = data
        msg = (
            "✅ <b>Данные отправлены</b>\n"
            "──────────────────\n"
            f"📅 <b>Дата:</b> {d['Date_Day']}.{d['Date_Month']}.{d['Date_Year']}\n"
            f"👤 <b>Клиент:</b> {d.get('Customer_Name', '—')}\n"
            f"🆔 <b>ID:</b> {d.get('Customer_ID', '—')}\n"
            f"🏢 <b>Buyer:</b> {d.get('Buyer', '—')}\n"
            "──────────────────\n"
            f"🚗 <b>Лот:</b> {d.get('Lot', '—')}\n"
            f"🚙 <b>Авто:</b> {d.get('Vehicle', '—')}\n"
            f"🔢 <b>VIN:</b> {d.get('Vin', '—')}\n"
            "──────────────────\n"
            f"💰 <b>Amount:</b> ${d.get('Amount_USD', '—')}\n"
            f"💸 <b>Fee:</b> ${d.get('Auction_Fee', '—')}\n"
            f"💵 <b>Total:</b> ${d.get('Total_USD', '—')}\n"
            "──────────────────\n"
            "⏳ Документы будут готовы через ~2 минуты"
        )
        safe_send_message(chat_id, msg, parse_mode='HTML')

        lot = d.get('Lot', '')

        def send_reminder():
            time.sleep(120)
            rows = fetch_invoices()
            row = next((r for r in reversed(rows) if r.get('Lot', '').strip() == lot.strip()), None)
            if row:
                doc_types = get_doc_types_from_row(row)
                show_doc_type_selector(chat_id, lot, doc_types)
            else:
                safe_send_message(chat_id, f"⏰ Документы для лота <b>{lot}</b> готовы.\nИспользуйте /docs для просмотра.", parse_mode='HTML')

        threading.Thread(target=send_reminder, daemon=True).start()

    except Exception:
        safe_send_message(chat_id, "❌ Ошибка")

# ── Buyer callbacks ────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: call.data.startswith('buyer_'))
def handle_buyer_selection(call):
    try:
        chat_id = call.message.chat.id
        if chat_id not in user_state or user_state[chat_id].get('waiting_for') != 'buyer_selection':
            safe_answer_callback(call.id, "Ошибка состояния")
            return

        buyer_val = call.data[len('buyer_'):]

        if buyer_val == 'other':
            safe_answer_callback(call.id, "Введите номер")
            safe_send_message(chat_id, "✏️ Введите номер Buyer:")
            user_state[chat_id]['waiting_for'] = 'Buyer_manual'
        else:
            user_state[chat_id]['data']['Buyer'] = buyer_val
            safe_answer_callback(call.id, f"✓ {buyer_val}")
            safe_send_message(chat_id, f"✅ Buyer: <b>{buyer_val}</b>", parse_mode='HTML')
            time.sleep(0.5)
            ask_customer_type(chat_id)
    except Exception:
        safe_answer_callback(call.id, "Ошибка")

@bot.callback_query_handler(func=lambda call: call.data in ['customer_regular', 'customer_new'])
def handle_customer_type_selection(call):
    try:
        chat_id = call.message.chat.id
        if chat_id not in user_state or user_state[chat_id].get('waiting_for') != 'customer_type_selection':
            return

        if call.data == 'customer_regular':
            user_state[chat_id]['data']['Customer_Name'] = REGULAR_CUSTOMER['name']
            user_state[chat_id]['data']['Customer_ID'] = REGULAR_CUSTOMER['id']
            safe_answer_callback(call.id, "Постоянный клиент")
            safe_send_message(
                chat_id,
                f"✅ <b>{REGULAR_CUSTOMER['name']}</b>\nID: {REGULAR_CUSTOMER['id']}",
                parse_mode='HTML'
            )
            time.sleep(0.5)
            safe_send_message(chat_id, "💸 Введите Auction Fee:")
            user_state[chat_id]['waiting_for'] = 'Auction_Fee'
        else:
            safe_answer_callback(call.id, "Новый клиент")
            safe_send_message(chat_id, "👤 Введите Customer Name:")
            user_state[chat_id]['waiting_for'] = 'Customer_Name'
    except Exception:
        safe_answer_callback(call.id, "Ошибка")

# ── /docs command ──────────────────────────────────────────────────────────────

def build_docs_keyboard(recent, rows_offset, selected):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for i, row in enumerate(recent):
        lot = row.get('Lot', 'N/A')
        vehicle = (row.get('Vehicle', '') or '')[:22]
        date = (row.get('Date', '') or '')[:10]
        actual_index = rows_offset + i
        check = '☑' if actual_index in selected else '☐'
        keyboard.add(types.InlineKeyboardButton(
            text=f"{check} {lot} | {vehicle} | {date}",
            callback_data=f"toggle_{actual_index}"
        ))
    keyboard.add(types.InlineKeyboardButton(
        text=f"📤 Выбрать документ ({len(selected)})",
        callback_data="send_docs"
    ))
    return keyboard

@bot.message_handler(commands=['docs'])
def handle_docs(message):
    chat_id = message.chat.id
    safe_send_message(chat_id, "⏳ Загружаю список...")

    rows = fetch_invoices()
    if not rows:
        safe_send_message(chat_id, "❌ Не удалось загрузить список")
        return

    recent = rows[-15:]
    rows_offset = len(rows) - len(recent)

    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['selected_docs'] = set()
    user_state[chat_id]['docs_rows'] = recent
    user_state[chat_id]['docs_offset'] = rows_offset
    user_state[chat_id]['all_rows'] = rows

    keyboard = build_docs_keyboard(recent, rows_offset, set())
    safe_send_message(
        chat_id,
        f"📋 <b>Последние {len(recent)} инвойсов</b>\nВыберите один или несколько:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_'))
def handle_toggle(call):
    chat_id = call.message.chat.id
    index = int(call.data.split('_')[1])

    if chat_id not in user_state or 'selected_docs' not in user_state[chat_id]:
        safe_answer_callback(call.id, "Начните заново — /docs")
        return

    selected = user_state[chat_id]['selected_docs']
    if index in selected:
        selected.discard(index)
        safe_answer_callback(call.id, "Снято")
    else:
        selected.add(index)
        safe_answer_callback(call.id, "Выбрано ✓")

    keyboard = build_docs_keyboard(
        user_state[chat_id]['docs_rows'],
        user_state[chat_id]['docs_offset'],
        selected
    )
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=keyboard)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == 'send_docs')
def handle_send_docs(call):
    chat_id = call.message.chat.id
    safe_answer_callback(call.id, "Загружаю...")

    if chat_id not in user_state or not user_state[chat_id].get('selected_docs'):
        safe_send_message(chat_id, "❌ Ничего не выбрано")
        return

    selected = sorted(user_state[chat_id]['selected_docs'])
    all_rows = user_state[chat_id].get('all_rows', [])

    for index in selected:
        if index >= len(all_rows):
            continue
        row = all_rows[index]
        lot = row.get('Lot', f'#{index}')
        doc_types = get_doc_types_from_row(row)
        show_doc_type_selector(chat_id, lot, doc_types)
        time.sleep(0.5)

    user_state[chat_id]['selected_docs'] = set()

# ── File & text handlers ───────────────────────────────────────────────────────

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
    safe_send_message(chat_id, "✅ Инвойс получен\n\n🚗 Введите LOT:")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if text.startswith('/start'):
        safe_send_message(
            chat_id,
            "🤖 <b>Auto Invoice Bot</b>\n\n"
            "📤 Отправьте PDF или фото инвойса\n"
            "📋 /docs — список документов",
            parse_mode='HTML'
        )
        return

    if chat_id not in user_state:
        safe_send_message(chat_id, "📤 Отправьте PDF или фото инвойса")
        return

    waiting = user_state[chat_id].get('waiting_for')

    if waiting == 'Lot':
        user_state[chat_id]['data']['Lot'] = text
        safe_send_message(chat_id, f"✅ LOT: <b>{text}</b>\n\n🔢 Введите VIN:", parse_mode='HTML')
        user_state[chat_id]['waiting_for'] = 'Vin'

    elif waiting == 'Vin':
        user_state[chat_id]['data']['Vin'] = text
        safe_send_message(chat_id, f"✅ VIN: <b>{text}</b>\n\n🚙 Введите авто:", parse_mode='HTML')
        user_state[chat_id]['waiting_for'] = 'Vehicle'

    elif waiting == 'Vehicle':
        user_state[chat_id]['data']['Vehicle'] = text
        safe_send_message(chat_id, f"✅ Авто: <b>{text}</b>\n\n💰 Введите Amount USD:", parse_mode='HTML')
        user_state[chat_id]['waiting_for'] = 'Amount_USD'

    elif waiting == 'Amount_USD':
        user_state[chat_id]['data']['Amount_USD'] = text
        safe_send_message(chat_id, f"✅ Amount: <b>${text}</b>", parse_mode='HTML')
        time.sleep(0.5)
        ask_buyer_selection(chat_id)

    elif waiting == 'Buyer_manual':
        user_state[chat_id]['data']['Buyer'] = text
        safe_send_message(chat_id, f"✅ Buyer: <b>{text}</b>", parse_mode='HTML')
        time.sleep(0.5)
        ask_customer_type(chat_id)

    elif waiting == 'Customer_Name':
        user_state[chat_id]['data']['Customer_Name'] = text
        safe_send_message(chat_id, f"✅ Клиент: <b>{text}</b>\n\n🆔 Введите Customer ID:", parse_mode='HTML')
        user_state[chat_id]['waiting_for'] = 'Customer_ID'

    elif waiting == 'Customer_ID':
        user_state[chat_id]['data']['Customer_ID'] = text
        safe_send_message(chat_id, f"✅ ID: <b>{text}</b>\n\n💸 Введите Auction Fee:", parse_mode='HTML')
        user_state[chat_id]['waiting_for'] = 'Auction_Fee'

    elif waiting == 'Auction_Fee':
        try:
            fee = float(text.replace(',', '').replace(' ', ''))
            amount = float(
                user_state[chat_id]['data'].get('Amount_USD', '0')
                .replace(',', '').replace('$', '').replace(' ', '')
            )
            total = round(amount + fee, 2)

            user_state[chat_id]['data']['Auction_Fee'] = str(fee)
            user_state[chat_id]['data']['Total_USD'] = str(total)

            safe_send_message(
                chat_id,
                f"✅ Fee: <b>${fee}</b> | Total: <b>${total}</b>\n\n📤 Отправляю...",
                parse_mode='HTML'
            )

            success = submit_to_google_form(user_state[chat_id]['data'])
            if success:
                send_completion_message(chat_id, user_state[chat_id]['data'])
            else:
                safe_send_message(chat_id, "❌ Ошибка отправки в Google Form")

            user_state.pop(chat_id, None)

        except ValueError:
            safe_send_message(chat_id, "❌ Введите число, например: 625.00")

# ── Start ──────────────────────────────────────────────────────────────────────

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
