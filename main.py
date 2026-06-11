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

print("Bot starting...")

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8760516717:AAFjIvQTVgWIM2wJQVlRBEped4rM6fAakLM')
BOT_PASSWORD = os.environ.get('BOT_PASSWORD', 'Hybridi2026')
bot = telebot.TeleBot(BOT_TOKEN)
user_state = {}
authorized_users = set()

GOOGLE_FORM_SUBMIT_URL = "https://docs.google.com/forms/d/e/1FAIpQLScNSb3c7aTOaaWPU-glnLQlhHdbpIL2EC-me7HevJ2yZnlbdw/formResponse"
GOOGLE_FORM_VIEW_URL  = "https://docs.google.com/forms/d/e/1FAIpQLScNSb3c7aTOaaWPU-glnLQlhHdbpIL2EC-me7HevJ2yZnlbdw/viewform"
SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/1TZLP0-nmPEICQsXXQuipnov9tR4JVWeC4aRu8I-KzWw/export?format=csv&gid=1152025982"

GOOGLE_FORM_FIELDS = {
    'Date_Year':    'entry.2136135204_year',
    'Date_Month':   'entry.2136135204_month',
    'Date_Day':     'entry.2136135204_day',
    'Customer_Name':'entry.21018057',
    'Customer_ID':  'entry.1116307930',
    'Lot':          'entry.1163357354',
    'Vehicle':      'entry.341377459',
    'Vin':          'entry.1094744061',
    'Amount_USD':   'entry.1342000086',
    'Auction_Fee':  'entry.532543637',
    'Total_USD':    'entry.857168306',
    'Buyer':        'entry.784567376'
}

BULK_PROMPT = (
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

# ── Invoice start keyboard ─────────────────────────────────────────────────────

def invoice_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📎 Загрузить файл", callback_data="inv_upload"),
        types.InlineKeyboardButton("✏️ Ввести вручную", callback_data="inv_manual")
    )
    return keyboard

def start_bulk_input(chat_id):
    now = datetime.now()
    user_state[chat_id] = {
        'data': {
            'Date_Year':  str(now.year),
            'Date_Month': str(now.month),
            'Date_Day':   str(now.day)
        },
        'waiting_for': 'bulk_input'
    }
    safe_send_message(chat_id, BULK_PROMPT)

@bot.callback_query_handler(func=lambda call: call.data in ['inv_upload', 'inv_manual'])
def handle_invoice_choice(call):
    chat_id = call.message.chat.id
    if call.data == 'inv_manual':
        safe_answer_callback(call.id, "Ввод вручную")
        start_bulk_input(chat_id)
    else:
        safe_answer_callback(call.id, "Отправьте файл")
        safe_send_message(chat_id, "📎 Отправьте PDF или фото инвойса")

# ── Google Sheets ──────────────────────────────────────────────────────────────

def fetch_invoices():
    try:
        response = requests.get(SHEETS_CSV_URL, allow_redirects=True, timeout=30)
        content = response.content.decode('utf-8-sig')
        all_rows = list(csv.reader(io.StringIO(content)))
        if not all_rows:
            return []
        headers = all_rows[0]
        result = []
        for raw in all_rows[1:]:
            d = {}
            for i, h in enumerate(headers):
                if h not in d and i < len(raw):
                    d[h] = raw[i]
            d['_raw'] = raw
            result.append(d)
        return result
    except Exception:
        return []

def clean_doc_name(name):
    if '<<' in name:
        name = name[:name.index('<<')]
    return name.strip()

def last_data_row(rows):
    for row in reversed(rows):
        cells = row.get('_raw', list(row.values()))
        for cell in cells:
            if isinstance(cell, str) and (
                cell.startswith('https://drive.google.com/') or
                cell.startswith('https://docs.google.com/')
            ):
                return row
    for row in reversed(rows):
        lot = row.get('Lot', '') or ''
        customer = row.get('Customer_Name', '') or ''
        if lot.strip() or customer.strip():
            return row
    return rows[-1] if rows else None

def get_doc_types_from_row(row):
    cells = row.get('_raw', list(row.values())) if isinstance(row, dict) else row
    doc_types = []
    seen_urls = set()

    for i, value in enumerate(cells):
        value = (value or '').strip()
        if value in seen_urls:
            continue
        if not (value.startswith('https://drive.google.com/') or
                value.startswith('https://docs.google.com/')):
            continue
        seen_urls.add(value)

        name = None
        for j in range(1, 4):
            if i + j >= len(cells):
                break
            candidate = (cells[i + j] or '').strip()
            if (candidate
                    and not candidate.startswith('http')
                    and 'Document successfully' not in candidate
                    and 'Starting at' not in candidate
                    and 'Run via' not in candidate
                    and 'Timestamp:' not in candidate
                    and len(candidate) >= 3
                    and len(candidate) < 150):
                name = clean_doc_name(candidate)
                break

        if not name:
            name = f"Document {len(doc_types) + 1}"

        doc_types.append((name, value))

    return doc_types

# ── Google Drive download ──────────────────────────────────────────────────────

def download_drive_file(url):
    try:
        file_id = None
        is_doc = False

        if '/file/d/' in url:
            file_id = url.split('/file/d/')[1].split('/')[0].split('?')[0]
        elif '/document/d/' in url:
            file_id = url.split('/document/d/')[1].split('/')[0].split('?')[0]
            is_doc = True
        elif '/spreadsheets/d/' in url:
            file_id = url.split('/spreadsheets/d/')[1].split('/')[0].split('?')[0]
            is_doc = True
        elif '/presentation/d/' in url:
            file_id = url.split('/presentation/d/')[1].split('/')[0].split('?')[0]
            is_doc = True
        elif 'open?id=' in url:
            file_id = url.split('open?id=')[1].split('&')[0]
        elif 'id=' in url:
            file_id = url.split('id=')[1].split('&')[0]

        if not file_id:
            return None

        if is_doc:
            if '/spreadsheets/d/' in url:
                dl_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=pdf"
            elif '/presentation/d/' in url:
                dl_url = f"https://docs.google.com/presentation/d/{file_id}/export/pdf"
            else:
                dl_url = f"https://docs.google.com/document/d/{file_id}/export?format=pdf"
        else:
            dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        session = requests.Session()
        resp = session.get(dl_url, allow_redirects=True, timeout=60)

        if resp.status_code == 200 and b'%PDF' not in resp.content[:1024]:
            match = re.search(rb'confirm=([0-9A-Za-z_-]+)', resp.content)
            if match:
                confirm = match.group(1).decode()
                resp = session.get(f"{dl_url}&confirm={confirm}", allow_redirects=True, timeout=60)

        if resp.status_code == 200 and b'%PDF' in resp.content[:1024]:
            return resp.content

        return None
    except Exception:
        return None

def send_pdf_to_user(chat_id, name, url):
    safe_send_message(chat_id, f"Загружаю: <b>{name}</b>...", parse_mode='HTML')
    content = download_drive_file(url)
    if content:
        try:
            file_obj = io.BytesIO(content)
            file_obj.name = f"{name}.pdf"
            bot.send_document(chat_id, file_obj, caption=name)
            return
        except Exception:
            pass
    safe_send_message(chat_id, f"<b>{name}</b>\n{url}", parse_mode='HTML')

# ── Document selector ──────────────────────────────────────────────────────────

def show_doc_type_selector(chat_id, label, doc_types, lot_key=''):
    if not doc_types:
        safe_send_message(chat_id, "⏳ Документы ещё не готовы — попробуйте /docs через минуту")
        return

    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['current_doc_types'] = doc_types
    user_state[chat_id]['current_doc_selected'] = set()
    user_state[chat_id]['current_lot_key'] = lot_key

    keyboard = build_doctype_keyboard(doc_types, set(), lot_key)
    safe_send_message(
        chat_id,
        f"📄 <b>{label}</b>\nВыберите нужные:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

def build_doctype_keyboard(doc_types, selected, lot_key=''):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for i, (name, url) in enumerate(doc_types):
        check = '[x]' if i in selected else '[ ]'
        keyboard.add(types.InlineKeyboardButton(
            text=f"{check} {name[:45]}",
            callback_data=f"dtoggle_{i}"
        ))
    keyboard.add(types.InlineKeyboardButton(
        text=f"Отправить выбранные ({len(selected)})",
        callback_data="dtsendsel"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="Отправить все",
        callback_data="dtsendall"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="Обновить список",
        callback_data=f"dtrefresh_{lot_key}"
    ))
    return keyboard

@bot.callback_query_handler(func=lambda call: call.data.startswith('dtrefresh_'))
def handle_doctype_refresh(call):
    chat_id = call.message.chat.id
    lot_key = call.data[len('dtrefresh_'):]
    safe_answer_callback(call.id, "Обновляю...")

    rows = fetch_invoices()
    if not rows:
        safe_send_message(chat_id, "Не удалось загрузить данные")
        return

    if lot_key and lot_key != 'last':
        row = next(
            (r for r in reversed(rows)
             if lot_key.strip() in [str(c).strip() for c in r.get('_raw', [])]),
            None
        )
        if not row:
            row = last_data_row(rows)
    else:
        row = last_data_row(rows)

    vehicle = row.get('Vehicle', '') or ''
    date    = row.get('Date', '') or ''
    lot     = row.get('Lot', '') or ''
    label   = f"{vehicle} | {date}" if vehicle else date
    doc_types = get_doc_types_from_row(row)

    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id]['current_doc_types'] = doc_types
    user_state[chat_id]['current_doc_selected'] = set()
    user_state[chat_id]['current_lot_key'] = lot_key

    keyboard = build_doctype_keyboard(doc_types, set(), lot_key)
    try:
        bot.edit_message_text(
            f"📄 <b>{label}</b>\nВыберите нужные: ({len(doc_types)} документов)",
            chat_id, call.message.message_id,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception:
        safe_send_message(chat_id, f"📄 <b>{label}</b>\nВыберите нужные:",
                          reply_markup=keyboard, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('dtoggle_'))
def handle_doctype_toggle(call):
    chat_id = call.message.chat.id
    idx = int(call.data.split('_')[1])

    doc_types = user_state.get(chat_id, {}).get('current_doc_types', [])
    selected  = user_state.get(chat_id, {}).get('current_doc_selected', set())

    if idx in selected:
        selected.discard(idx)
        safe_answer_callback(call.id, "Снято")
    else:
        selected.add(idx)
        safe_answer_callback(call.id, "Выбрано")

    user_state[chat_id]['current_doc_selected'] = selected
    keyboard = build_doctype_keyboard(doc_types, selected)
    try:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=keyboard)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == 'dtsendsel')
def handle_doctype_send_selected(call):
    chat_id = call.message.chat.id
    safe_answer_callback(call.id, "Отправляю...")

    doc_types = user_state.get(chat_id, {}).get('current_doc_types', [])
    selected  = user_state.get(chat_id, {}).get('current_doc_selected', set())

    if not selected:
        safe_send_message(chat_id, "Ничего не выбрано")
        return

    for i in sorted(selected):
        if i < len(doc_types):
            name, url = doc_types[i]
            send_pdf_to_user(chat_id, name, url)
            time.sleep(0.5)

    user_state[chat_id]['current_doc_selected'] = set()
    safe_send_message(chat_id, "Следующий инвойс?", reply_markup=invoice_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == 'dtsendall')
def handle_doctype_send_all(call):
    chat_id = call.message.chat.id
    safe_answer_callback(call.id, "Отправляю все...")

    doc_types = user_state.get(chat_id, {}).get('current_doc_types', [])
    if not doc_types:
        safe_send_message(chat_id, "Документы не найдены")
        return

    for name, url in doc_types:
        send_pdf_to_user(chat_id, name, url)
        time.sleep(0.5)

    safe_send_message(chat_id, "Следующий инвойс?", reply_markup=invoice_keyboard())

# ── Google Form ────────────────────────────────────────────────────────────────

def submit_to_google_form(data):
    try:
        form_data = {
            entry_id: str(data[field])
            for field, entry_id in GOOGLE_FORM_FIELDS.items()
            if field in data and data[field]
        }
        form_data['fvv'] = '1'
        form_data['fbzx'] = str(int(time.time() * 1000))
        form_data['pageHistory'] = '0'

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': GOOGLE_FORM_VIEW_URL,
        })
        session.get(GOOGLE_FORM_VIEW_URL, timeout=15)

        response = session.post(
            GOOGLE_FORM_SUBMIT_URL,
            data=form_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            allow_redirects=True,
            timeout=30
        )
        print(f"[FORM] Status: {response.status_code}")
        return response.status_code in [200, 302]
    except Exception as e:
        print(f"[FORM] Exception: {e}")
        return False

def send_completion_message(chat_id, data):
    try:
        d = data
        msg = (
            "✅ <b>Данные отправлены</b>\n"
            "──────────────────\n"
            f"📅 Дата: {d['Date_Day']}.{d['Date_Month']}.{d['Date_Year']}\n"
            f"👤 Клиент: {d.get('Customer_Name', '—')}\n"
            f"🆔 ID: {d.get('Customer_ID', '—')}\n"
            f"🏢 Buyer: {d.get('Buyer', '—')}\n"
            "──────────────────\n"
            f"🚗 Лот: {d.get('Lot', '—')}\n"
            f"🚙 Авто: {d.get('Vehicle', '—')}\n"
            f"🔢 VIN: {d.get('Vin', '—')}\n"
            "──────────────────\n"
            f"💰 Amount: ${d.get('Amount_USD', '—')}\n"
            f"💸 Fee: ${d.get('Auction_Fee', '—')}\n"
            f"💵 Total: ${d.get('Total_USD', '—')}\n"
            "──────────────────\n"
            "⏳ Документы будут готовы через ~2 минуты"
        )
        safe_send_message(chat_id, msg, parse_mode='HTML')

        lot     = d.get('Lot', '')
        vehicle = d.get('Vehicle', '')

        def send_reminder():
            time.sleep(120)
            rows = fetch_invoices()
            row = next(
                (r for r in reversed(rows)
                 if lot.strip() and lot.strip() in [str(c).strip() for c in r.get('_raw', [])]),
                None
            )
            if not row:
                row = last_data_row(rows)
            if row:
                doc_types = get_doc_types_from_row(row)
                label = f"{lot} | {vehicle}"
                show_doc_type_selector(chat_id, label, doc_types, lot_key=lot)
            else:
                safe_send_message(chat_id, f"Документы для лота <b>{lot}</b> — используйте /docs",
                                  parse_mode='HTML')

        threading.Thread(target=send_reminder, daemon=True).start()

    except Exception:
        safe_send_message(chat_id, "Ошибка")

# ── /docs ──────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['docs'])
def handle_docs(message):
    chat_id = message.chat.id
    safe_send_message(chat_id, "Загружаю...")

    rows = fetch_invoices()
    if not rows:
        safe_send_message(chat_id, "Не удалось загрузить данные")
        return

    row = last_data_row(rows)
    if not row:
        safe_send_message(chat_id, "Нет данных в таблице")
        return

    vehicle = row.get('Vehicle', '') or ''
    date    = row.get('Date', '') or ''
    lot     = row.get('Lot', '') or ''
    label   = f"{vehicle} | {date}" if vehicle else date
    doc_types = get_doc_types_from_row(row)
    show_doc_type_selector(chat_id, label, doc_types, lot_key=lot or 'last')

# ── File & text handlers ───────────────────────────────────────────────────────

@bot.message_handler(content_types=['document', 'photo'])
def handle_file(message):
    chat_id = message.chat.id
    if chat_id not in authorized_users:
        safe_send_message(chat_id, "🔒 Введите пароль:")
        return
    safe_send_message(chat_id, "Инвойс получен")
    start_bulk_input(chat_id)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if text.startswith('/start'):
        if chat_id in authorized_users:
            safe_send_message(
                chat_id,
                "<b>Auto Invoice Bot</b>\n\n"
                "Новый инвойс:",
                reply_markup=invoice_keyboard(),
                parse_mode='HTML'
            )
        else:
            safe_send_message(chat_id, "🔒 Введите пароль:")
        return

    if chat_id not in authorized_users:
        if text == BOT_PASSWORD:
            authorized_users.add(chat_id)
            safe_send_message(
                chat_id,
                "✅ Доступ открыт\n\n"
                "<b>Auto Invoice Bot</b>\n\n"
                "Новый инвойс:",
                reply_markup=invoice_keyboard(),
                parse_mode='HTML'
            )
        else:
            safe_send_message(chat_id, "❌ Неверный пароль. Попробуйте ещё раз:")
        return

    if chat_id not in user_state:
        safe_send_message(chat_id, "Новый инвойс:", reply_markup=invoice_keyboard())
        return

    waiting = user_state[chat_id].get('waiting_for')

    if waiting == 'bulk_input':
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) < 8:
            safe_send_message(
                chat_id,
                f"Нужно 8 строк, получено {len(lines)}. Попробуйте ещё раз:\n\n{BULK_PROMPT}"
            )
            return
        try:
            amount = float(lines[3].replace(',', '').replace('$', '').replace(' ', ''))
            fee    = float(lines[7].replace(',', '').replace(' ', ''))
            total  = round(amount + fee, 2)
        except ValueError:
            safe_send_message(chat_id, "Amount и Auction Fee должны быть числами. Попробуйте ещё раз:\n\n" + BULK_PROMPT)
            return

        d = user_state[chat_id]['data']
        d['Lot']           = lines[0]
        d['Vin']           = lines[1]
        d['Vehicle']       = lines[2]
        d['Amount_USD']    = str(amount)
        d['Buyer']         = lines[4]
        d['Customer_Name'] = lines[5]
        d['Customer_ID']   = lines[6]
        d['Auction_Fee']   = str(fee)
        d['Total_USD']     = str(total)

        safe_send_message(
            chat_id,
            f"✅ LOT: <b>{d['Lot']}</b>\n"
            f"✅ VIN: <b>{d['Vin']}</b>\n"
            f"✅ Авто: <b>{d['Vehicle']}</b>\n"
            f"💰 Amount: <b>${amount}</b>  |  Fee: <b>${fee}</b>  |  Total: <b>${total}</b>\n"
            f"🏢 Buyer: <b>{d['Buyer']}</b>\n"
            f"👤 {d['Customer_Name']}  |  {d['Customer_ID']}\n\n"
            f"📤 Отправляю...",
            parse_mode='HTML'
        )

        success = submit_to_google_form(d)
        if success:
            send_completion_message(chat_id, d)
        else:
            safe_send_message(chat_id, "Ошибка отправки в Google Form")

        user_state.pop(chat_id, None)

# ── Start ──────────────────────────────────────────────────────────────────────

print("Started at:", datetime.now())

try:
    bot.delete_webhook(drop_pending_updates=True)
    print("Webhook cleared")
except Exception as e:
    print(f"Webhook clear error: {e}")

time.sleep(2)

while True:
    try:
        print("Bot polling started...")
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        print(f"Bot error: {e}")
        print("Restarting in 5 seconds...")
        time.sleep(5)
