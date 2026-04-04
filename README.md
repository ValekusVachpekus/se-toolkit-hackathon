# 🏠 ЖКХ Bot - Telegram Bot + Web Panel

Система приёма жалоб от жителей на проблемы в ЖКХ.

## Demo

### Screenshots

**Веб-панель администратора:**
<img width="3070" height="1516" alt="изображение" src="https://github.com/user-attachments/assets/89dc83b0-a245-4dc4-ae1c-75a307db782c" />
<img width="3070" height="1508" alt="изображение" src="https://github.com/user-attachments/assets/f37d3514-9aa9-4cf8-964c-6c0cb81799e4" />
<img width="3070" height="1514" alt="изображение" src="https://github.com/user-attachments/assets/d10b1942-05de-4a7e-ba05-eb591401b452" />
<img width="3070" height="1514" alt="изображение" src="https://github.com/user-attachments/assets/b8629919-9604-4cbf-a430-851af02d1dbb" />
<img width="3070" height="1514" alt="изображение" src="https://github.com/user-attachments/assets/c8ff9244-0523-4686-a008-03e9c4fd9baf" />

**Веб-панель работника:**
<img width="3070" height="1510" alt="изображение" src="https://github.com/user-attachments/assets/d392ccb1-78c9-455d-a89f-0be2e716c1c9" />


**Telegram бот - подача жалобы:**
<img width="1258" height="1496" alt="изображение" src="https://github.com/user-attachments/assets/d7cd1358-f7be-4d32-85d9-afcbf3b27ebf" />
<img width="762" height="342" alt="изображение" src="https://github.com/user-attachments/assets/7ca50cf1-21d8-4369-b213-494ba3355e40" />
<img width="822" height="560" alt="изображение" src="https://github.com/user-attachments/assets/689190d4-4cca-4592-a173-75d7029569e7" />


**Веб-панель пользователя:**
<img width="2116" height="1512" alt="изображение" src="https://github.com/user-attachments/assets/692828b4-a212-4499-b3bd-073babc85ea0" />

## Функциолнал

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
- 🔗 **Вход** - по одноразовому коду из Telegram (`/link_account`)

### Веб-панель пользователя (жителя)
- 📋 **Мои жалобы** - список всех жалоб со статусами и оценками
- 📝 **Подать жалобу** - форма подачи (ФИО, адрес, описание, загрузка фото/видео или ссылка)
- 📄 **Детали жалобы** - просмотр статуса, информации о работнике, причины отказа
- ⭐ **Оценка работы** - оценка качества выполненной работы (1-5 звёзд + отзыв)
- 🔗 **Вход** - по одноразовому коду из Telegram (`/link_account`)

## Технологии

- **Bot**: Python 3.12, aiogram 3.15
- **Web**: FastAPI, Jinja2, Tailwind CSS, Chart.js
- **Database**: SQLite (aiosqlite)
- **Deploy**: Docker Compose
- **Notifications**: aiohttp (Telegram Bot API)

## Структура проекта

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
│       └── user/            # Шаблоны пользователя
│           ├── complaints.html
│           ├── complaint_form.html
│           ├── complaint_detail.html
│           └── rate.html
├── data/                    # БД + медиа (создаётся автоматически)
├── logs/                    # Логи (создаётся автоматически)
├── docker-compose.yml
├── Dockerfile.bot
├── Dockerfile.web
├── requirements.txt
└── .env.example
```

## База данных

SQLite с таблицами:
- `complaints` — жалобы (id, user_id, fio, address, description, media, status, rating, review, rejection_reason...)
- `employees` — работники (user_id, username, fio, position, area, registered, web_linked)
- `blocked_users` — заблокированные пользователи
- `complaint_messages` — ID сообщений для инвалидации кнопок
- `verification_codes` — коды для связи аккаунта с веб-панелью

## Запуск

### Требования

- **ОС**: Ubuntu 24.04 (или совместимая Linux система)
- **Docker**: 24.0 или новее
- **Docker Compose**: v2.0 или новее

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

**Использование**
- Telegram бот: напишите `/start`
- Веб-панель админа: http://localhost:8000 (пароль из `ADMIN_PASSWORD`)
- Веб-панель работника: http://localhost:8000 (код из `/link_account` в боте)
- Веб-панель пользователя: http://localhost:8000 (код из `/link_account` в боте)

Жалобы, поданные через веб-панель, автоматически отправляются работникам в Telegram с кнопками для обработки.

### Остановить
```bash
docker compose down
```

## Deployment

### Развертывание на VM

#### Системные требования

- **ОС**: Ubuntu 24.04 LTS
- **Установленное ПО**:
  - Docker Engine 24.0+
  - Docker Compose v2+
  - Git

#### Пошаговая инструкция

1. **Установить Docker и Docker Compose** (если не установлены):
   ```bash
   # Обновить пакеты
   sudo apt update
   
   # Установить Docker
   sudo apt install -y docker.io docker-compose-v2
   
   # Добавить пользователя в группу docker
   sudo usermod -aG docker $USER
   newgrp docker
   ```

2. **Клонировать репозиторий**:
   ```bash
   git clone https://github.com/ValekusVachpekus/se-toolkit-hackathon.git
   cd se-toolkit-hackathon
   ```

3. **Настроить переменные окружения**:
   ```bash
   cp .env.example .env
   nano .env  # или используйте любой текстовый редактор
   ```
   
   Обязательно заполните:
   - `BOT_TOKEN` - токен от @BotFather
   - `ADMIN_ID` - ваш Telegram ID
   - `ADMIN_PASSWORD` - пароль для веб-панели
   - `SECRET_KEY` - случайная строка для сессий
   - `LOG_CHAT_ID` - (опционально) ID группы для архива

4. **Создать необходимые директории**:
   ```bash
   mkdir -p data logs
   chmod 777 data logs
   ```

5. **Запустить приложение**:
   ```bash
   docker compose up -d --build
   ```

6. **Проверить статус**:
   ```bash
   docker compose ps
   docker compose logs -f
   ```

7. **Доступ к приложению**:
   - Telegram бот: напишите `/start` вашему боту
   - Веб-панель: `http://<IP_вашего_VM>:8000`

#### Обновление приложения

```bash
cd se-toolkit-hackathon
git pull
docker compose down
docker compose up -d --build
```

#### Остановка приложения

```bash
docker compose down
```

#### Полная очистка (включая данные)

```bash
docker compose down -v
rm -rf data logs
```

## Команды Telegram-бота

### Для жителей
| Команда | Описание |
|---------|----------|
| `/start` | Начало работы |
| `/complaint` | Подать жалобу (4 шага) |
| `/rate` | Оценить выполненную работу |
| `/link_account` | Получить код для входа в веб-панель |

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

## Веб-панель

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

### Панель пользователя (`/user/*`)
- **Мои жалобы** (`/user/complaints`) - список всех жалоб со статусами
- **Подать жалобу** (`/user/complaints/new`) - форма с загрузкой медиа
- **Детали жалобы** (`/user/complaints/{id}`) - полная информация, статус, работник
- **Оценить работу** (`/user/complaints/{id}/rate`) - оценка 1-5 звёзд + отзыв

## Реализовано

- [x] Telegram бот с FSM
- [x] Подача жалоб (ФИО, адрес, описание, медиа)
- [x] Панель администратора
- [x] Панель работника
- [x] Панель пользователя (жителя)
- [x] Система рейтингов (1-5 звёзд + отзыв)
- [x] Графики на дашборде
- [x] Уведомления через Telegram API
- [x] Архивирование в лог-группу
- [x] Вход работника/пользователя по коду
- [x] Загрузка медиа в Telegram из веб-панели
- [x] Инвалидация кнопок после обработки жалобы

## TODO

- [ ] Экспорт жалоб в CSV/Excel
- [ ] PostgreSQL для production
- [ ] Push-уведомления в веб-панели
- [ ] Публичная форма подачи жалоб

## Лицензия

[MIT License](LICENSE) 

## Автор

 - GitHub: [ValekusVachpekus]([url](https://github.com/ValekusVachpekus))
 - Электронная почта: i.shchetkov@innopolis.university
 - ФИО: Щетков Илья Алексеевич (Shchetkov Ilia Alexeevich)

Создано в рамках учебного проекта в курсе Software Engeneering Toolkit в Innopolis University

