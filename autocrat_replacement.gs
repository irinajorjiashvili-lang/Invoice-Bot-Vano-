// ═══════════════════════════════════════════════════════════════
// КОНФИГУРАЦИЯ
// ═══════════════════════════════════════════════════════════════

const TEMPLATE_IDS = [
  '1b00INgqdIkWcGWKK7c1MmbXnhnJ-zsHw-iINL_3ZVLA',
  '1v1o8JTBg0ROEqPKXskYxrE_VrwBs1NW-bTLZC3xgzFc',
  '1sH2hJx3DJ6Ll3YVNDeVVAbhyTS96IVHxwpM1zhq-YY4',
  '1YSIyov6jTHWtTwrvcJXaZkxUBHLW4Rqlz7n51TlLBg0',
  '1wlSM2WIe-jOeT1ZHqUjp5Lr2Pw5tXG7f232dqvlNamI',
  '1D5oELPwMBHEgsQ6y425y7LVe-28vU-3hnVzzAvLTINo',
  '1hxf2_N-JDDByzy3Ea1YJ2pfbqnVXuAWIIyPxOl5OkDs',
  '17sLRKKoRGUnj5Vsw53JC0O83uX8ylzjyZI7jqChOMb0',
  '10tb-Ms9yHw6SEb6upGBpDmjh-efoOV_79_WzG_2USxE',
  '1FHHGyei-It1hciPJvyPUAHb81NpjLJl2y-dlugmZfig',
];

const OUTPUT_FOLDER_ID = '16TbdEUM8qYdxzYC7heUwe6vIXJQV2wEK';

// GID вкладки с ответами (из ссылки на таблицу: ...&gid=1152025982)
const RESPONSE_SHEET_GID = 1152025982;

// ═══════════════════════════════════════════════════════════════
// ОСНОВНАЯ ФУНКЦИЯ — запускается автоматически при новой записи
// ═══════════════════════════════════════════════════════════════

function generateDocuments(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // Найти нужную вкладку по GID
  const sheet = ss.getSheets().find(s => s.getSheetId() === RESPONSE_SHEET_GID);
  if (!sheet) {
    Logger.log('Вкладка не найдена. Проверьте RESPONSE_SHEET_GID.');
    return;
  }

  // Пропускаем события не связанные с добавлением строк
  if (e && e.changeType && e.changeType !== 'INSERT_ROW') return;

  // Всегда обрабатываем последнюю строку (бот добавляет строку через API)
  const row = sheet.getLastRow();
  if (row <= 1) return;

  // Проверяем — не обработана ли строка уже (есть ли ссылки на документы)
  const checkVal = sheet.getRange(row, 14).getValue();
  if (checkVal && String(checkVal).startsWith('http')) {
    Logger.log('Строка ' + row + ' уже обработана, пропускаем.');
    return;
  }

  // Читаем заголовки (строка 1)
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  // Читаем данные строки
  const values = sheet.getRange(row, 1, 1, lastCol).getValues()[0];

  // Строим карту тегов: <<Заголовок>> → значение
  const data = {};
  headers.forEach((h, i) => {
    const key = String(h).trim();
    if (key) data[key] = String(values[i] !== undefined ? values[i] : '');
  });

  Logger.log('Данные строки ' + row + ': ' + JSON.stringify(data));

  const folder = DriveApp.getFolderById(OUTPUT_FOLDER_ID);

  // Колонка, с которой начинаем писать ссылки
  // (первая пустая колонка в заголовке)
  let linkStartCol = 1;
  for (let i = 0; i < headers.length; i++) {
    if (String(headers[i]).trim() !== '') linkStartCol = i + 2;
    else break;
  }

  // Обрабатываем каждый шаблон
  for (let i = 0; i < TEMPLATE_IDS.length; i++) {
    const templateId = TEMPLATE_IDS[i];
    try {
      const templateFile = DriveApp.getFileById(templateId);
      const templateName = templateFile.getName();

      // Копируем шаблон в папку
      const copy = templateFile.makeCopy('_tmp_', folder);
      copy.setTrashed(false); // на случай если шаблон в корзине
      const doc = DocumentApp.openById(copy.getId());
      const body = doc.getBody();

      // Заменяем все теги <<Заголовок>> реальными значениями
      Object.entries(data).forEach(([key, val]) => {
        body.replaceText('<<' + key + '>>', val);
      });

      doc.saveAndClose();

      // Переименовываем файл — заменяем теги в имени шаблона
      const finalName = templateName.replace(/<<([^>]+)>>/g, (_, tag) => data[tag] || '');
      copy.setName(finalName);

      // Записываем URL и имя в ОТДЕЛЬНЫЕ ячейки
      // (бот читает CSV: ищет ячейку с https://, следующая — имя документа)
      const url = 'https://docs.google.com/document/d/' + copy.getId() + '/view';
      const col = linkStartCol + i * 2;
      sheet.getRange(row, col).setValue(url);
      sheet.getRange(row, col + 1).setValue(finalName);

      Logger.log('Создан документ: ' + finalName + ' → ' + url);

    } catch (err) {
      Logger.log('Ошибка шаблона ' + templateId + ': ' + err.toString());
    }
  }

  Logger.log('Строка ' + row + ' обработана.');
}

// ═══════════════════════════════════════════════════════════════
// УСТАНОВКА ТРИГГЕРА — запустить ОДИН РАЗ вручную
// ═══════════════════════════════════════════════════════════════

function setupTrigger() {
  // Удаляем старые триггеры
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // Создаём триггер на изменение таблицы (добавление строки через API)
  ScriptApp.newTrigger('generateDocuments')
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onChange()
    .create();

  Logger.log('Триггер установлен успешно.');
  SpreadsheetApp.getUi().alert('Триггер установлен! Скрипт будет запускаться при каждой новой записи.');
}

// ═══════════════════════════════════════════════════════════════
// ТЕСТ — запустить вручную для проверки на последней строке
// ═══════════════════════════════════════════════════════════════

function testOnLastRow() {
  generateDocuments(null);
}
