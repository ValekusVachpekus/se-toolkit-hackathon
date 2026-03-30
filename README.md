# 🏠 ЖКХ Bot - Telegram Bot + Web Panel

Система приёма жалоб от жителей на проблемы в ЖКХ.

## 🎯 Возможности

### Telegram Bot
- **Пользователи** - подают жалобы (ФИО, адрес, суть проблемы, фото/видео)
- **Работники** - принимают/отклоняют жалобы
- **Администратор** - управляет работниками, обрабатывает жалобы
- **Система рейтинга** - жители оценивают качество работы (1-5 ⭐)
- Блокировка пользователей
- Уведомления о статусе жалобы с информацией о работнике
- Архивирование обработанных жалоб в архив-группу

### Веб-панель администратора
- 📊 **Дашборд** - статистика, графики (Chart.js)
- 📋 **Жалобы** - список жалоб с фильтрами, поиском, пагинацией, принятие/отклонение жалоб с уведомлениями
- 👷 **Работники** - добавление/удаление сотрудников
- ⭐ **Рейтинги** - статистика работников, отзывы
- 🚫 **Заблокированные** - управление заблокированными пользователями

### Веб-панель работника
- 📋 **Жалобы** - список жалоб с фильтрами, поиском, пагинацией, возможность принимать/отклонять жалобы
- ⭐ **Рейтинги** - статистика работников, отзывы
- 🔗 **Вход** -  по одноразовому коду из Telegram (`/link_account`)

## 🛠 Технологии

- **Bot**: Python 3.12, aiogram 3.15
- **Web**: FastAPI, Jinja2, Tailwind CSS, Chart.js
- **Database**: SQLite (aiosqlite)
- **Deploy**: Docker Compose
- **Notifications**: aiohttp (Telegram Bot API)

## 📁 Структура проекта

```
Toolkit-tg-bot/
├── bot/
│   ├── main.py              # Точка входа бота
│   ├── config.py            # Конфигурация (env)
│   ├── database.py          # Инициализация БД, миграции
│   ├── states.py            # FSM состояния
│   ├── keyboards.py         # Inline клавиатуры
│   ├── media_utils.py       # Скачивание медиа
│   ├── logging_config.py    # Настройка логов
│   └── handlers/
│       ├── user.py          # Команды жителей (/complaint, /rate)
│       ├── employee.py      # Команды работников (/register, /link_account)
│       └── admin.py         # Команды админа (/add_employee, /staff)
├── web/
│   ├── main.py              # FastAPI приложение
│   ├── auth.py              # Аутентификация (admin/employee)
│   ├── config.py            # Конфигурация веб-панели
│   ├── database.py          # SQLite подключение
│   ├── logging_config.py    # Логирование
│   ├── static/              # CSS стили
│   └── templates/
│       ├── base.html        # Базовый шаблон
│       ├── login.html       # Страница входа
│       ├── admin/           # Шаблоны админа
│       │   ├── dashboard.html
│       │   ├── complaints.html
│       │   ├── complaint_detail.html
│       │   ├── employees.html
│       │   ├── ratings.html
│       │   └── blocked.html
│       └── employee/        # Шаблоны работника
│           ├── complaints.html
│           ├── complaint_detail.html
│           └── ratings.html
├── data/                    # БД + медиа (создаётся автоматически)
├── logs/                    # Логи (создаётся автоматически)
├── docker-compose.yml
├── Dockerfile.bot
├── Dockerfile.web
├── requirements.txt
└── .env.example
```

## 🗃 База данных

SQLite с таблицами:
- `complaints` — жалобы (id, user_id, fio, address, description, media, status, rating, review, rejection_reason...)
- `employees` — работники (user_id, username, fio, position, area, registered, web_linked)
- `blocked_users` — заблокированные пользователи
- `complaint_messages` — ID сообщений для инвалидации кнопок
- `verification_codes` — коды для связи аккаунта с веб-панелью

## 🚀 Быстрый старт

### 1. Настроить переменные окружения
```bash
cp .env.example .env
```

Отредактировать `.env`:
```env
BOT_TOKEN=your_bot_token          # Токен от @BotFather
ADMIN_ID=123456789                # Ваш Telegram ID
LOG_CHAT_ID=-100123456789         # ID группы-архива (опционально)
ADMIN_PASSWORD=secure_password    # Пароль админа для веб-панели
SECRET_KEY=random_secret_key      # Секретный ключ для сессий
DB_PATH=data/complaints.db        # Путь к базе данных
```

**Как получить BOT_TOKEN:** [@BotFather](https://t.me/BotFather) → `/newbot`

**Как узнать ADMIN_ID:** [@userinfobot](https://t.me/userinfobot)

**Как получить LOG_CHAT_ID:** Создайте группу, добавьте бота, отправьте сообщение и проверьте через API

### 2. Запустить через Docker
```bash
docker compose up -d --build
```

**Готово!**
- Telegram бот: напишите `/start`
- Веб-панель админа: http://localhost:8000 (пароль из `ADMIN_PASSWORD`)
- Веб-панель работника: http://localhost:8000 (код из `/link_account` в боте)

### Остановить
```bash
docker compose down
```

## 📱 Команды бота

### Для жителей
| Команда | Описание |
|---------|----------|
| `/start` | Начало работы |
| `/complaint` | Подать жалобу (4 шага) |
| `/rate` | Оценить выполненную работу |

### Для работников
| Команда | Описание |
|---------|----------|
| `/register` | Регистрация (после добавления админом) |
| `/complaints` | Активные жалобы |
| `/link_account` | Получить код для входа в веб-панель |

### Для администратора
| Команда | Описание |
|---------|----------|
| `/add_employee` | Добавить работника по username |
| `/staff` | Список работников |
| `/complaints` | Активные жалобы |
| `/blocked` | Заблокированные пользователи |

## 🌐 Веб-панель

### Вход
- **Администратор**: пароль из `.env`
- **Работник**: одноразовый 6-значный код из команды `/link_account`

### Админ-панель (`/admin/*`)
- **Дашборд** - карточки статистики + 3 графика (pie, bar, line)
- **Жалобы** - фильтры по статусу, поиск, пагинация
- **Детали жалобы** - медиа, принятие/отклонение с причиной
- **Работники** - добавление/удаление
- **Рейтинги** - средний рейтинг работников, последние отзывы
- **Заблокированные** - список заблокировнных пользователей и возможность разблокировки

### Панель работника (`/employee/*`)
- **Жалобы** - просмотр, принятие/отклонение
- **Рейтинги** - общая статистика

## ✅ Реализовано

- [x] Telegram бот с FSM
- [x] Подача жалоб (ФИО, адрес, описание, медиа)
- [x] Панель администратора
- [x] Панель работника
- [x] Система рейтингов (1-5 звёзд + отзыв)
- [x] Графики на дашборде
- [x] Уведомления через Telegram API
- [x] Архивирование в лог-группу
- [x] Вход работника по коду

## 📝 TODO

- [ ] Экспорт жалоб в CSV/Excel
- [ ] PostgreSQL для production
- [ ] Push-уведомления в веб-панели
- [ ] Публичная форма подачи жалоб

## 📄 Лицензия

[GPL v3.0](LICENSE) 

## 👤 Автор

 - GitHub: [ValekusVachpekus]([url](https://github.com/ValekusVachpekus))
 - Электронная почта: i.shchetkov@innopolis.university
 - ФИО: Щетков Илья Алексеевич (Shchetkov Ilia Alexeevich)

Создано в рамках учебного проекта в курсе Software Engeneering Toolkit в Innopolis University

