# Copyright (C) 2026 Shchetkov Ilia
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import ADMIN_ID, DB_PATH
from bot.database import get_all_recipient_ids, is_blocked
from bot.keyboards import build_complaint_text
from bot.logging_config import get_logger
from bot.media_utils import download_media
from bot.states import ComplaintForm, RatingForm

router = Router()
logger = get_logger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    uid = message.from_user.id
    username = (message.from_user.username or "").lower()

    if uid == ADMIN_ID:
        await message.answer(
            "🏠 <b>Добро пожаловать в систему приёма жалоб ЖКХ, Администратор!</b>\n\n"
            "Команды:\n"
            "/add_employee — добавить работника\n"
            "/staff — список работников\n"
            "/blocked — заблокированные пользователи\n"
            "/complaints — активные жалобы",
            parse_mode="HTML",
        )
        return

    if await is_blocked(uid):
        await message.answer("❌ Вы заблокированы и не можете использовать этого бота.")
        return

    # Auto-link employee by username on first /start
    if username:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, registered FROM employees WHERE username=?", (username,)
            ) as cur:
                row = await cur.fetchone()
        if row:
            emp_uid, registered = row
            if not emp_uid:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE employees SET user_id=? WHERE username=?", (uid, username))
                    await db.commit()
            if not registered:
                await message.answer(
                    "👋 Вы добавлены как работник службы ЖКХ.\n"
                    "Пройдите регистрацию командой /register"
                )
            else:
                await message.answer(
                    "🔧 <b>Добро пожаловать, работник службы ЖКХ!</b>\n\n"
                    "Команды:\n"
                    "/complaints — активные жалобы\n"
                    "/register — пройти регистрацию заново\n"
                    "/link_account — получить код для входа в веб-панель",
                    parse_mode="HTML",
                )
            return

    await message.answer(
        "👋 Добро пожаловать в <b>Веб-приёмную жалоб ЖКХ</b>!\n\n"
        "Здесь вы можете сообщить о проблемах с коммунальными услугами: "
        "протечки, отопление, электричество, уборка и т.д.\n\n"
        "Команды:\n"
        "/complaint — подать жалобу (4 шага)\n"
        "/rate — оценить выполненную работу\n"
        "/link_account — получить код для входа в веб-панель\n\n"
        "В веб-панели вы можете:\n"
        "• Подать жалобу с фото/видео\n"
        "• Просматривать статусы всех жалоб\n"
        "• Оценивать качество работы",
        parse_mode="HTML",
    )


@router.message(Command("complaint"))
async def cmd_complaint(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if await is_blocked(uid):
        await message.answer("❌ Вы заблокированы и не можете использовать этого бота.")
        return
    await state.set_state(ComplaintForm.fio)
    await message.answer(
        "📝 <b>Подача жалобы ЖКХ</b>\n\nШаг 1/4: Введите ваше ФИО:",
        parse_mode="HTML",
    )


@router.message(ComplaintForm.fio)
async def process_fio(message: Message, state: FSMContext) -> None:
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    await state.update_data(fio=message.text)
    await state.set_state(ComplaintForm.address)
    await message.answer("Шаг 2/4: Введите адрес (улица, дом, корпус, квартира):")


@router.message(ComplaintForm.address)
async def process_address(message: Message, state: FSMContext) -> None:
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    await state.update_data(address=message.text)
    await state.set_state(ComplaintForm.description)
    await message.answer("Шаг 3/4: Опишите суть жалобы (что сломалось, не работает, требует ремонта):")


@router.message(ComplaintForm.description)
async def process_description(message: Message, state: FSMContext) -> None:
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    await state.update_data(description=message.text)
    await state.set_state(ComplaintForm.media)
    await message.answer(
        "Шаг 4/4: Прикрепите фото или видео проблемы (по желанию):\n"
        "• фото или видео\n"
        "• или отправьте ссылку\n"
        "(или /skip чтобы пропустить):"
    )


@router.message(ComplaintForm.media, Command("skip"))
async def skip_media(message: Message, state: FSMContext) -> None:
    await _submit_complaint(message, state, None, None)


@router.message(ComplaintForm.media, F.text)
async def process_media_link(message: Message, state: FSMContext) -> None:
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    text = message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        await message.answer("❌ Это не ссылка. Отправьте фото, видео или ссылку (начинающуюся с http:// или https://), либо /skip чтобы пропустить.")
        return
    await _submit_complaint(message, state, text, "link")


@router.message(ComplaintForm.media, F.photo | F.video | F.document)
async def process_media(message: Message, state: FSMContext) -> None:
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    if message.photo:
        fid, ftype = message.photo[-1].file_id, "photo"
    elif message.video:
        fid, ftype = message.video.file_id, "video"
    else:
        fid, ftype = message.document.file_id, "document"
    await _submit_complaint(message, state, fid, ftype)


async def _submit_complaint(
    message: Message, state: FSMContext,
    media_file_id: str | None, media_type: str | None,
) -> None:
    from bot.handlers.employee import send_complaint_to_all
    
    data = await state.get_data()
    await state.clear()

    uid = message.from_user.id
    username = message.from_user.username
    fio = data.get("fio", "")
    address = data.get("address", "")
    description = data.get("description", "")
    
    # Download media file if present
    media_local_path = None
    if media_file_id and media_type != "link":
        media_local_path = await download_media(message.bot, media_file_id, media_type, uid)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO complaints (user_id, username, fio, address, description, media_file_id, media_type, media_local_path)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (uid, username, fio, address, description, media_file_id, media_type, media_local_path),
        )
        complaint_id = cur.lastrowid
        await db.commit()
        recipients = await get_all_recipient_ids(db)

    logger.info(
        "📨 Новая жалоба #%d от пользователя %d (@%s): %s | %s",
        complaint_id, uid, username or "без username", fio, address[:50]
    )

    await message.answer(f"✅ Ваша жалоба №{complaint_id} успешно отправлена на рассмотрение. Работник будет направлен для устранения проблемы.")

    # Дополнительное уведомление о том, как отследить жалобу
    await message.answer(
        "📌 <b>Статус вашей жалобы:</b>\n\n"
        "• Жалоба отправлена работникам\n"
        "• Вы получите уведомление, когда работник примет жалобу\n"
        "• После выполнения работы вы сможете оценить качество командой /rate\n\n"
        "Спасибо за обращение!",
        parse_mode="HTML"
    )

    uname = f"@{username}" if username else "без username"
    text = build_complaint_text(complaint_id, uname, uid, fio, address, description)
    await send_complaint_to_all(message.bot, complaint_id, text, media_file_id, media_type, recipients)


# ---------------------------------------------------------------------------
# Rating system
# ---------------------------------------------------------------------------

@router.message(Command("rate"))
async def cmd_rate(message: Message, state: FSMContext) -> None:
    """Start rating process for user"""
    if await is_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы.")
        return
    
    uid = message.from_user.id
    
    # Find last accepted complaint without rating
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM complaints WHERE user_id=? AND status='accepted' AND rating IS NULL ORDER BY created_at DESC LIMIT 1",
            (uid,)
        )
        complaint = await cursor.fetchone()
    
    if not complaint:
        await message.answer("❌ У вас нет принятых жалоб для оценки.")
        return
    
    complaint_id = complaint[0]
    await state.set_state(RatingForm.rating)
    await state.update_data(complaint_id=complaint_id)
    
    await message.answer(
        f"⭐ <b>Оценка жалобы #{complaint_id}</b>\n\n"
        "Оцените качество выполненной работы от 1 до 5:\n"
        "1 - Очень плохо\n"
        "2 - Плохо\n"
        "3 - Удовлетворительно\n"
        "4 - Хорошо\n"
        "5 - Отлично\n\n"
        "Отправьте цифру от 1 до 5:",
        parse_mode="HTML"
    )


@router.message(RatingForm.rating)
async def process_rating(message: Message, state: FSMContext) -> None:
    """Process star rating (1-5)"""
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    
    try:
        rating = int(message.text.strip())
        if not 1 <= rating <= 5:
            raise ValueError()
    except (ValueError, AttributeError):
        await message.answer("❌ Пожалуйста, отправьте цифру от 1 до 5.")
        return
    
    await state.update_data(rating=rating)
    await state.set_state(RatingForm.review)
    
    stars = "⭐" * rating
    await message.answer(
        f"{stars}\n\n"
        "Спасибо за оценку! Теперь напишите отзыв о выполненной работе.\n\n"
        "Или отправьте /skip чтобы пропустить отзыв.",
        parse_mode="HTML"
    )


@router.message(RatingForm.review, Command("skip"))
async def skip_review(message: Message, state: FSMContext) -> None:
    """Skip review and save rating"""
    data = await state.get_data()
    complaint_id = data.get("complaint_id")
    rating = data.get("rating")
    
    await state.clear()
    
    uid = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE complaints SET rating=?, rated_at=datetime('now') WHERE id=?",
            (rating, complaint_id)
        )
        await db.commit()
    
    logger.info(f"⭐ Жалоба #{complaint_id} оценена на {rating} звезд (без отзыва) пользователем {uid}")
    
    await message.answer(
        f"✅ Спасибо за оценку!\n\n"
        f"{'⭐' * rating}\n\n"
        "Ваше мнение поможет улучшить качество обслуживания."
    )


@router.message(RatingForm.review)
async def process_review(message: Message, state: FSMContext) -> None:
    """Save rating with review text"""
    if await is_blocked(message.from_user.id):
        await state.clear()
        await message.answer("❌ Вы заблокированы.")
        return
    
    data = await state.get_data()
    complaint_id = data.get("complaint_id")
    rating = data.get("rating")
    review = message.text.strip()
    
    await state.clear()
    
    uid = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE complaints SET rating=?, review=?, rated_at=datetime('now') WHERE id=?",
            (rating, review, complaint_id)
        )
        await db.commit()
    
    logger.info(f"⭐ Жалоба #{complaint_id} оценена на {rating} звезд пользователем {uid} с отзывом: {review[:100]}")
    
    await message.answer(
        f"✅ Спасибо за оценку и отзыв!\n\n"
        f"{'⭐' * rating}\n\n"
        f'"{review}"\n\n'
        "Ваше мнение поможет улучшить качество обслуживания."
    )


# ---------------------------------------------------------------------------
# Link account for web panel (for regular users)
# ---------------------------------------------------------------------------

@router.message(Command("link_account"))
async def cmd_link_account_user(message: Message) -> None:
    """Generate verification code for linking account to web panel (for both users and employees)"""
    uid = message.from_user.id
    username = message.from_user.username or "no_username"
    
    if await is_blocked(uid):
        await message.answer("❌ Вы заблокированы.")
        return
    
    # Check if this is an employee
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, registered FROM employees WHERE user_id=?",
            (uid,)
        )
        emp = await cursor.fetchone()
        
        # Generate 6-digit code
        import random
        code = f"{random.randint(100000, 999999)}"
        
        # Save to DB with 10-minute expiry
        from datetime import datetime, timedelta
        expires = datetime.now() + timedelta(minutes=10)
        
        if emp:
            # Employee - check if registered
            if not emp[1]:  # not registered
                await message.answer("❌ Вы не зарегистрированы как работник.\nИспользуйте /register для регистрации.")
                return
            
            role = "employee"
            try:
                await db.execute(
                    "INSERT INTO verification_codes (code, user_id, username, expires_at, role) VALUES (?, ?, ?, ?, ?)",
                    (code, uid, username, expires, role)
                )
                await db.commit()
            except Exception:
                # Code already exists, delete and retry
                await db.execute("DELETE FROM verification_codes WHERE code=?", (code,))
                await db.execute(
                    "INSERT INTO verification_codes (code, user_id, username, expires_at, role) VALUES (?, ?, ?, ?, ?)",
                    (code, uid, username, expires, role)
                )
                await db.commit()
            
            logger.info(f"🔗 Код подтверждения {code} сгенерирован для работника {username} ({uid})")
            
            await message.answer(
                f"🔗 <b>Связь аккаунта с веб-панелью</b>\n\n"
                f"Ваш код подтверждения: <code>{code}</code>\n\n"
                f"Перейдите на веб-панель и введите этот код для входа как работник.\n"
                f"Код действует 10 минут.",
                parse_mode="HTML"
            )
        else:
            # Regular user
            role = "user"
            try:
                await db.execute(
                    "INSERT INTO verification_codes (code, user_id, username, expires_at, role) VALUES (?, ?, ?, ?, ?)",
                    (code, uid, username, expires, role)
                )
                await db.commit()
            except Exception:
                # Code already exists, delete and retry
                await db.execute("DELETE FROM verification_codes WHERE code=?", (code,))
                await db.execute(
                    "INSERT INTO verification_codes (code, user_id, username, expires_at, role) VALUES (?, ?, ?, ?, ?)",
                    (code, uid, username, expires, role)
                )
                await db.commit()
            
            logger.info(f"🔗 Код подтверждения {code} сгенерирован для пользователя {username} ({uid})")
            
            await message.answer(
                f"🔗 <b>Связь аккаунта с веб-панелью</b>\n\n"
                f"Ваш код подтверждения: <code>{code}</code>\n\n"
                f"Перейдите на веб-панель и введите этот код для входа как житель.\n"
                f"Код действует 10 минут.",
                parse_mode="HTML"
            )
