Личный телеграм-бот «Заметки + Напоминания» (python-telegram-bot 21 + APScheduler)

Запуск локально
1. Установите Python 3.10+
2. Создайте виртуальное окружение и установите зависимости:
   pip install -r requirements.txt
3. Установите переменную окружения TELEGRAM_TOKEN (токен бота от @BotFather)
4. Запустите:
   python -m bot.main

Команды
- /start — помощь
- /ping — проверить
- /note <текст>
- /notes
- /find <подстрока>
- /remind <текст> | <YYYY-MM-DD HH:MM или "через 30м">
- /reminders
- /web <запрос> — web-поиск через Tavily
- /ask <вопрос> — ответ через Cloudflare Workers AI (короткая память)
- /shell <cmd> — минимальная автоматизация ПК (в проде выключено)

Примеры
- /note купить молоко
- /find мол
- /remind Позвонить | 2026-07-20 18:30
- /remind Чайник выключить | через 20м
 - /web новости ИИ сегодня
 - /ask Как начать учить Go?

Деплой на Render (free)
- Добавлен render.yaml и Procfile.
- Переменные окружения в Render Dashboard: TELEGRAM_TOKEN, CF_API_TOKEN, CF_ACCOUNT_ID, TAVILY_API_KEY.
- ENABLE_SHELL=false для безопасности.
