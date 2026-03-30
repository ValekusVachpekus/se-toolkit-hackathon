# Copyright (C) 2026 Shchetkov Ilia
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import ADMIN_ID, DB_PATH
from bot.logging_config import get_logger
from bot.states import AddEmployeeForm

router = Router()
logger = get_logger(__name__)


@router.message(Command("add_employee"))
async def cmd_add_employee(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AddEmployeeForm.username)
    await message.answer("Введите Telegram username сотрудника (с @ или без):")


@router.message(AddEmployeeForm.username)
async def process_add_employee(message: Message, state: FSMContext) -> None:
    await state.clear()
    username = message.text.lstrip("@").lower().strip()
    if not username:
        await message.answer("❌ Некорректный username.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM employees WHERE username=?", (username,)) as cur:
            exists = await cur.fetchone()
        if exists:
            await message.answer(f"⚠️ Работник @{username} уже добавлен.")
            return
        await db.execute("INSERT INTO employees (username) VALUES (?)", (username,))
        await db.commit()

    logger.info("➕ Администратор добавил работника: @%s", username)
    
    await message.answer(
        f"✅ Работник @{username} добавлен.\n"
        "Пусть он напишет /start боту, чтобы связать аккаунт, затем пройдёт /register."
    )


@router.message(Command("staff"))
async def cmd_staff(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, fio, position, area, registered FROM employees ORDER BY added_at DESC"
        ) as cur:
            employees = await cur.fetchall()

    if not employees:
        await message.answer("📋 Список работников пуст.")
        return

    await message.answer("🔧 <b>Работники службы ЖКХ:</b>", parse_mode="HTML")
    for user_id, username, fio, position, area, registered in employees:
        text = f"👤 <b>@{username}</b>\n"
        if registered:
            text += (
                f"✅ Зарегистрирован\n"
                f"📋 ФИО: {fio or '—'}\n"
                f"🏷 Должность: {position or '—'}\n"
                f"📍 Участок: {area or '—'}"
            )
        else:
            text += "⏳ Ожидает регистрации (нужно написать /start и /register)"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_employee_{username}"),
        ]])
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("del_employee_"))
async def delete_employee(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    username = callback.data.split("_", 2)[2]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM employees WHERE username=?", (username,))
        await db.commit()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(f"🗑 Работник @{username} удалён.")
    await callback.answer()


@router.message(Command("blocked"))
async def cmd_blocked(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, blocked_at FROM blocked_users ORDER BY blocked_at DESC"
        ) as cur:
            users = await cur.fetchall()

    if not users:
        await message.answer("📋 Список заблокированных пользователей пуст.")
        return

    await message.answer("🚫 <b>Заблокированные пользователи:</b>", parse_mode="HTML")
    for user_id, username, blocked_at in users:
        uname = f"@{username}" if username else f"ID: {user_id}"
        text = f"<code>{user_id}</code> ({uname})\n🕐 {str(blocked_at)[:16]}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔓 Разблокировать", callback_data=f"unblock_{user_id}"),
        ]])
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("unblock_"))
async def unblock_user(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    user_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM blocked_users WHERE user_id=?", (user_id,))
        await db.commit()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply(
        f"🔓 Пользователь <code>{user_id}</code> разблокирован.", parse_mode="HTML"
    )
    await callback.answer()
