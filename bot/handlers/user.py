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
                    "/register — пройти регистрацию заново",
                    parse_mode="HTML",
                )
            return

    await message.answer(
        "👋 Добро пожаловать в <b>Веб-приёмную жалоб ЖКХ</b>!\n\n"
        "Здесь вы можете сообщить о проблемах с коммунальными услугами: "
        "протечки, отопление, электричество, уборка и т.д.\n\n"
        "Используйте /complaint чтобы подать жалобу.",
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
