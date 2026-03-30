# 🚀 Инструкция по запуску

## Быстрый старт

1. **Убедитесь что Docker установлен:**
```bash
docker --version
docker compose version
```

2. **Пересоберите и запустите:**
```bash
sudo docker compose build
sudo docker compose up -d
```

3. **Проверьте статус:**
```bash
sudo docker compose ps
```

4. **Посмотрите логи:**
```bash
sudo docker compose logs -f bot
sudo docker compose logs -f web
```

5. **Откройте веб-панель:**
```
http://localhost:8000
Логин: admin
Пароль: admin123
```

---

## 🆕 Новые фичи в этой версии

### ⭐ Система рейтинга
- Пользователи могут оценить работу через `/rate`
- Веб-панель: новая страница `/ratings` с рейтингами работников
- Отображение средних оценок и отзывов

### 👷 Информация о работнике
- При принятии жалобы пользователь видит ФИО, должность и участок работника

### 🔔 Улучшенные уведомления
- Двойное уведомление при подаче жалобы
- Детальная информация при принятии

---

## 🧪 Тестирование новых фич

### Сценарий: Рейтинг
1. **Пользователь:** Подать жалобу `/complaint`
2. **Работник:** Принять жалобу (пользователь получит инфо о работнике)
3. **Пользователь:** `/rate` → выбрать 1-5 звезд → написать отзыв
4. **Админ:** http://localhost:8000/ratings → увидеть рейтинги

### Проверка логов рейтингов:
```bash
sudo docker compose logs bot | grep "⭐"
```

---

## 📁 Структура проекта

```
Toolkit-tg-bot/
├── bot/                    # Telegram бот
│   ├── handlers/           # Обработчики команд
│   │   ├── user.py         # Команды пользователей (/start, /complaint, /rate)
│   │   ├── employee.py     # Команды работников
│   │   └── admin.py        # Админские команды
│   ├── config.py           # Конфигурация
│   ├── database.py         # Работа с БД
│   ├── states.py           # FSM состояния
│   ├── keyboards.py        # Inline клавиатуры
│   ├── media_utils.py      # Обработка медиа
│   ├── logging_config.py   # Настройка логирования
│   └── main.py             # Точка входа
├── web/                    # Web панель
│   ├── templates/          # HTML шаблоны
│   │   ├── ratings.html    # ⭐ НОВОЕ: Страница рейтингов
│   │   └── ...
│   ├── static/             # CSS/JS
│   ├── config.py           # Конфигурация
│   ├── database.py         # Работа с БД
│   ├── auth.py             # Авторизация
│   ├── logging_config.py   # Настройка логирования
│   └── main.py             # FastAPI приложение
├── data/                   # База данных и медиа
│   ├── complaints.db       # SQLite база
│   └── media/              # Загруженные файлы
├── logs/                   # Логи (создается автоматически)
│   ├── bot.log
│   ├── bot_errors.log
│   ├── web.log
│   └── web_errors.log
├── docker-compose.yml      # Docker композиция
├── Dockerfile.bot          # Docker образ бота
├── Dockerfile.web          # Docker образ веб-панели
├── requirements.txt        # Python зависимости
├── README.md               # Основная документация
├── FEATURES_SUMMARY.md     # ⭐ Описание новых фич
└── DEPLOYMENT.md           # Эта инструкция
```

---

## 🔧 Если что-то пошло не так

### Проблема: Бот не отвечает
```bash
# Проверьте токен в docker-compose.yml
# Проверьте логи
sudo docker compose logs bot | tail -50
```

### Проблема: Веб-панель не открывается
```bash
# Проверьте что порт 8000 свободен
sudo netstat -tulpn | grep 8000

# Перезапустите контейнер
sudo docker compose restart web
```

### Проблема: База данных не обновилась
```bash
# Удалите старую БД и перезапустите
sudo docker compose down
rm data/complaints.db
sudo docker compose up -d

# Миграции применяются автоматически при запуске
```

### Полная переустановка:
```bash
sudo docker compose down
sudo docker system prune -a
rm -rf data/complaints.db logs/*.log
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## 📊 Мониторинг

### Посмотреть использование ресурсов:
```bash
sudo docker stats
```

### Посмотреть все логи:
```bash
sudo docker compose logs -f
```

### Посмотреть только ошибки:
```bash
sudo docker compose logs bot | grep ERROR
sudo docker compose logs web | grep ERROR
```

### Проверить размер БД:
```bash
ls -lh data/complaints.db
```

### Проверить размер логов:
```bash
du -sh logs/
```

---

## 🎯 Готово к демо!

Все фичи реализованы и готовы к показу на хакатоне. Просто запустите:

```bash
sudo docker compose up -d
```

И покажите жюри:
1. 📱 Telegram бот с подачей жалоб
2. 👷 Систему принятия с отображением информации о работнике  
3. ⭐ Рейтинг работников с отзывами
4. 💻 Красивую веб-панель
5. 📊 Статистику и аналитику

Удачи! 🚀
