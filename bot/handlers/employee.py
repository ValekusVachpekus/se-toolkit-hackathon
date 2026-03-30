import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import ADMIN_ID, DB_PATH, LOG_CHAT_ID
from bot.database import is_staff
from bot.keyboards import build_complaint_text, complaint_keyboard
from bot.logging_config import get_logger
from bot.states import EmployeeRegisterForm, RejectForm

router = Router()
logger = get_logger(__name__)


async def send_complaint_to_all(bot: Bot, complaint_id: int, text: str,
                                 media_file_id: str | None, media_type: str | None,
                                 recipients: list[int]) -> None:
    keyboard = complaint_keyboard(complaint_id)
    msg_rows = []
    for rid in recipients:
        try:
            if media_file_id and media_type != "link":
                send_fn = {
                    "photo": bot.send_photo,
                    "video": bot.send_video,
                    "document": bot.send_document,
                }.get(media_type, bot.send_document)
                sent = await send_fn(rid, media_file_id, caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                full_text = text + (f"\n🔗 <b>Доказательство:</b> {media_file_id}" if media_type == "link" else "")
                sent = await bot.send_message(rid, full_text, parse_mode="HTML", reply_markup=keyboard)
            msg_rows.append((complaint_id, rid, sent.message_id))
        except Exception as e:
            logger.warning("Could not send complaint to %s: %s", rid, e)

    if msg_rows:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(
                "INSERT INTO complaint_messages (complaint_id, chat_id, message_id) VALUES (?,?,?)",
                msg_rows,
            )
            await db.commit()


async def invalidate_complaint_messages(bot: Bot, complaint_id: int) -> None:
    """Remove inline keyboards from all complaint notification messages."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id, message_id FROM complaint_messages WHERE complaint_id=?",
            (complaint_id,),
        ) as cur:
            rows = await cur.fetchall()
    for chat_id, message_id in rows:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception:
            pass


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    username = (message.from_user.username or "").lower()

    if uid == ADMIN_ID:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM employees WHERE username=? OR user_id=?", (username, uid)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await message.answer("❌ Вы не добавлены как работник. Обратитесь к администратору.")
        return

    if username:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE employees SET user_id=? WHERE username=? AND (user_id IS NULL OR user_id=0)",
                (uid, username),
            )
            await db.commit()

    await state.set_state(EmployeeRegisterForm.fio)
    await message.answer(
        "📝 <b>Регистрация работника ЖКХ</b>\n\nШаг 1/3: Введите ваше ФИО:",
        parse_mode="HTML",
    )


@router.message(EmployeeRegisterForm.fio)
async def reg_fio(message: Message, state: FSMContext) -> None:
    await state.update_data(fio=message.text)
    await state.set_state(EmployeeRegisterForm.position)
    await message.answer("Шаг 2/3: Введите вашу должность (например: Сантехник, Электрик, Диспетчер):")


@router.message(EmployeeRegisterForm.position)
async def reg_position(message: Message, state: FSMContext) -> None:
    await state.update_data(position=message.text)
    await state.set_state(EmployeeRegisterForm.area)
    await message.answer("Шаг 3/3: Введите ваш участок/район обслуживания:")


@router.message(EmployeeRegisterForm.area)
async def reg_area(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    uid = message.from_user.id
    username = (message.from_user.username or "").lower()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE employees SET fio=?, position=?, area=?, registered=1, user_id=?"
            " WHERE username=? OR user_id=?",
            (data["fio"], data["position"], message.text, uid, username, uid),
        )
        await db.commit()

    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 ФИО: {data['fio']}\n"
        f"🏷 Должность: {data['position']}\n"
        f"📍 Участок: {message.text}\n\n"
        "Жалобы будут поступать к вам автоматически.\n"
        "Команды:\n/complaints — активные жалобы",
        parse_mode="HTML",
    )


@router.message(Command("complaints"))
async def cmd_complaints(message: Message) -> None:
    uid = message.from_user.id
    if not await is_staff(uid):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, username, fio, address, description, media_file_id, media_type"
            " FROM complaints WHERE status='pending' ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("📋 Нет активных жалоб.")
        return

    await message.answer(f"📋 <b>Активные жалобы ({len(rows)}):</b>", parse_mode="HTML")
    bot: Bot = message.bot
    for row in rows:
        cid, user_id, username, fio, address, description, fid, ftype = row
        uname = f"@{username}" if username else "без username"
        text = build_complaint_text(cid, uname, user_id, fio, address, description)
        keyboard = complaint_keyboard(cid)
        try:
            if fid:
                send_fn = {
                    "photo": bot.send_photo,
                    "video": bot.send_video,
                    "document": bot.send_document,
                }.get(ftype, bot.send_document)
                await send_fn(message.chat.id, fid, caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.warning("Error sending complaint %s: %s", cid, e)


@router.callback_query(F.data.startswith("accept_"))
async def accept_complaint(callback: CallbackQuery) -> None:
    if not await is_staff(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    complaint_id = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status FROM complaints WHERE id=?", (complaint_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await callback.answer("Жалоба не найдена.", show_alert=True)
            return
        user_id, status = row
        if status != "pending":
            await callback.answer("Эта жалоба уже обработана.", show_alert=True)
            return
        await db.execute(
            "UPDATE complaints SET status='accepted', accepted_by=? WHERE id=?",
            (callback.from_user.id, complaint_id),
        )
        await db.commit()
        
        # Получить инфо работника
        async with db.execute(
            "SELECT fio, position, area FROM employees WHERE user_id=?",
            (callback.from_user.id,)
        ) as cur:
            emp = await cur.fetchone()

    actor_name = callback.from_user.username or str(callback.from_user.id)
    logger.info(
        "✅ Жалоба #%d принята работником %d (@%s)",
        complaint_id, callback.from_user.id, actor_name
    )

    # Уведомление пользователю с инфо работника
    try:
        if emp:
            emp_fio, emp_position, emp_area = emp
            notification = (
                f"✅ <b>Ваша жалоба №{complaint_id} принята!</b>\n\n"
                f"Работник будет направлен для устранения проблемы.\n\n"
                f"👷 <b>Информация о работнике:</b>\n"
                f"📋 ФИО: {emp_fio or '—'}\n"
                f"🏷 Должность: {emp_position or '—'}\n"
                f"📍 Участок: {emp_area or '—'}\n\n"
                f"💡 После выполнения работы вы сможете оценить качество обслуживания."
            )
        else:
            notification = (
                f"✅ Ваша жалоба №{complaint_id} принята. Работник будет направлен для устранения проблемы.\n\n"
                f"💡 После выполнения работы вы сможете оценить качество обслуживания."
            )
        
        await callback.bot.send_message(user_id, notification, parse_mode="HTML")
    except Exception as e:
        logger.warning("Could not notify user %s: %s", user_id, e)

    await invalidate_complaint_messages(callback.bot, complaint_id)
    actor = callback.from_user.username or str(callback.from_user.id)
    await callback.message.reply(f"✅ Жалоба #{complaint_id} принята (@{actor}). Пользователь уведомлён.")
    await log_complaint_to_group(callback.bot, complaint_id, "принята",
                                  callback.from_user.id, callback.from_user.username)
    await callback.answer()


@router.callback_query(F.data.startswith("block_"))
async def block_user_callback(callback: CallbackQuery) -> None:
    if not await is_staff(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    complaint_id = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, status FROM complaints WHERE id=?", (complaint_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await callback.answer("Жалоба не найдена.", show_alert=True)
            return
        user_id, username, status = row
        if status != "pending":
            await callback.answer("Эта жалоба уже обработана.", show_alert=True)
            return
        await db.execute(
            "INSERT OR IGNORE INTO blocked_users (user_id, username) VALUES (?,?)",
            (user_id, username),
        )
        await db.execute(
            "UPDATE complaints SET status='blocked', accepted_by=? WHERE id=?",
            (callback.from_user.id, complaint_id),
        )
        await db.commit()

    uname = f"@{username}" if username else f"ID: {user_id}"
    actor_name = callback.from_user.username or str(callback.from_user.id)
    
    logger.warning(
        "🚫 Пользователь %d (@%s) заблокирован работником %d (@%s) по жалобе #%d",
        user_id, username or "нет", callback.from_user.id, actor_name, complaint_id
    )
    
    await invalidate_complaint_messages(callback.bot, complaint_id)
    actor = callback.from_user.username or str(callback.from_user.id)
    await callback.message.reply(f"🚫 Пользователь {uname} заблокирован (@{actor}).")
    await callback.answer()


@router.callback_query(F.data.startswith("reject_"))
async def reject_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_staff(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    complaint_id = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM complaints WHERE id=?", (complaint_id,)) as cur:
            row = await cur.fetchone()

    if not row:
        await callback.answer("Жалоба не найдена.", show_alert=True)
        return
    if row[0] != "pending":
        await callback.answer("Эта жалоба уже обработана.", show_alert=True)
        return

    await state.set_state(RejectForm.reason)
    await state.update_data(complaint_id=complaint_id)
    await callback.message.reply(f"✍️ Введите причину отклонения жалобы #{complaint_id}:")
    await callback.answer()


@router.message(RejectForm.reason)
async def reject_reason(message: Message, state: FSMContext) -> None:
    if not await is_staff(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    complaint_id = data.get("complaint_id")
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, status FROM complaints WHERE id=?", (complaint_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer("❌ Жалоба не найдена.")
            return
        user_id, status = row
        if status != "pending":
            await message.answer("⚠️ Эта жалоба уже обработана.")
            return
        await db.execute(
            "UPDATE complaints SET status='rejected', accepted_by=? WHERE id=?",
            (message.from_user.id, complaint_id),
        )
        await db.commit()

    actor_name = message.from_user.username or str(message.from_user.id)
    logger.info(
        "❌ Жалоба #%d отклонена работником %d (@%s). Причина: %s",
        complaint_id, message.from_user.id, actor_name, message.text[:100]
    )

    try:
        await message.bot.send_message(
            user_id,
            f"❌ Ваша жалоба №{complaint_id} отклонена.\n\n📝 <b>Причина:</b> {message.text}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Could not notify user %s: %s", user_id, e)

    await invalidate_complaint_messages(message.bot, complaint_id)
    actor = message.from_user.username or str(message.from_user.id)
    await message.answer(f"❌ Жалоба #{complaint_id} отклонена (@{actor}). Пользователь уведомлён.")
    await log_complaint_to_group(message.bot, complaint_id, "отклонена",
                                  message.from_user.id, message.from_user.username,
                                  reason=message.text)


async def log_complaint_to_group(
    bot: Bot,
    complaint_id: int,
    action: str,
    actor_id: int,
    actor_username: str | None,
    reason: str | None = None,
) -> None:
    if not LOG_CHAT_ID:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, fio, address, description, media_file_id, media_type"
            " FROM complaints WHERE id=?", (complaint_id,)
        ) as cur:
            c = await cur.fetchone()
        async with db.execute(
            "SELECT fio, position, area FROM employees WHERE user_id=?", (actor_id,)
        ) as cur:
            emp = await cur.fetchone()

    if not c:
        return

    user_id, username, fio, address, description, media_file_id, media_type = c

    action_emoji = "✅" if action == "принята" else "❌"
    actor_uname = f"@{actor_username}" if actor_username else f"ID: {actor_id}"
    uname = f"@{username}" if username else f"ID: {user_id}"

    header = f"{action_emoji} <b>Жалоба №{complaint_id} {action}</b> ({actor_uname})\n\n"
    complaint_text = (
        header
        + build_complaint_text(complaint_id, uname, user_id, fio, address, description).split("\n\n", 1)[1]
    )
    if reason:
        complaint_text += f"\n📝 <b>Причина отказа:</b> {reason}"
    if media_type == "link" and media_file_id:
        complaint_text += f"\n🔗 <b>Фото/видео:</b> {media_file_id}"

    try:
        if media_file_id and media_type != "link":
            send_fn = {
                "photo": bot.send_photo,
                "video": bot.send_video,
                "document": bot.send_document,
            }.get(media_type, bot.send_document)
            await send_fn(LOG_CHAT_ID, media_file_id)
        await bot.send_message(LOG_CHAT_ID, complaint_text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Could not send complaint card to log group: %s", e)
        return

    # Message 2: staff card
    if emp:
        emp_fio, emp_position, emp_area = emp
        staff_text = (
            f"🔧 <b>Карточка работника</b>\n\n"
            f"📋 ФИО: {emp_fio or '—'}\n"
            f"🏷 Должность: {emp_position or '—'}\n"
            f"📍 Участок: {emp_area or '—'}\n"
            f"🔗 Telegram: {actor_uname}"
        )
    else:
        staff_text = (
            f"🔧 <b>Карточка работника</b>\n\n"
            f"🔗 Telegram: {actor_uname}\n"
            f"🆔 ID: <code>{actor_id}</code>\n"
            f"(Администратор)"
        )
    try:
        await bot.send_message(LOG_CHAT_ID, staff_text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Could not send staff card to log group: %s", e)
