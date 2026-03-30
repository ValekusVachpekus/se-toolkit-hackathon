# Copyright (C) 2026 Shchetkov Ilia
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from datetime import datetime
import aiohttp
import os

from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.auth import check_auth, check_admin_auth, check_employee_auth, check_user_auth, get_user_role
from web.config import ADMIN_PASSWORD, MEDIA_DIR, SECRET_KEY
from web.database import get_db
from web.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="ЖКХ Панель")

templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "0"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: list | None = None) -> bool:
    """Send message via Telegram bot API"""
    if not BOT_TOKEN:
        logger.warning("⚠️ BOT_TOKEN not configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = {"inline_keyboard": reply_markup}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("result", {}).get("message_id")
                else:
                    logger.warning(f"⚠️ Failed to send message to {chat_id}: {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}")
        return None


async def upload_media_to_telegram(media_type: str, file_path: str) -> str | None:
    """Upload media file to Telegram and return file_id"""
    if not BOT_TOKEN:
        logger.warning("⚠️ BOT_TOKEN not configured, cannot upload media")
        return None

    try:
        logger.info(f"📤 Uploading {media_type} to Telegram: {file_path}")
        
        endpoint = {
            "photo": "sendPhoto",
            "video": "sendVideo",
            "document": "sendDocument",
        }.get(media_type, "sendDocument")

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"

        # Send to a dummy chat (we just need the file_id)
        # Use ADMIN_ID as dummy chat if available, otherwise use a placeholder
        dummy_chat_id = ADMIN_ID if ADMIN_ID else 123456789
        logger.info(f"   Using dummy chat_id: {dummy_chat_id}")

        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                form_data = aiohttp.FormData()
                form_data.add_field("chat_id", str(dummy_chat_id))
                form_data.add_field(media_type, f, filename=file_path.split('/')[-1])

                async with session.post(url, data=form_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # Extract file_id from the response
                        if media_type == "photo":
                            file_id = result["result"]["photo"][-1]["file_id"]
                        elif media_type == "video":
                            file_id = result["result"]["video"]["file_id"]
                        else:
                            file_id = result["result"]["document"]["file_id"]
                        logger.info(f"✅ Uploaded media to Telegram, file_id: {file_id[:20]}...")
                        return file_id
                    else:
                        logger.warning(f"⚠️ Failed to upload media: {resp.status}")
                        return None
    except Exception as e:
        logger.error(f"❌ Error uploading media: {e}")
        return None


async def send_media_message(chat_id: int, media_type: str, media_file_id: str, caption: str, reply_markup: list | None = None) -> int | None:
    """Send media message via Telegram Bot API.
    
    media_file_id can be:
    - Telegram file_id (e.g., "AgACAgIAAxkDAAIB...")
    - HTTP URL (e.g., "https://example.com/image.jpg")
    - Local file path (e.g., "123_abc.jpg")
    """
    if not BOT_TOKEN:
        return None

    try:
        # Determine the type of media_file_id
        is_url = media_file_id.startswith("http://") or media_file_id.startswith("https://")
        is_local_file = not is_url and "/" in media_file_id and "." in media_file_id.split("/")[-1]
        is_telegram_file_id = not is_url and not is_local_file and len(media_file_id) > 20
        
        endpoint = {
            "photo": "sendPhoto",
            "video": "sendVideo",
            "document": "sendDocument",
        }.get(media_type, "sendDocument")
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"
        
        if is_telegram_file_id:
            # Send using existing Telegram file_id
            data = {
                "chat_id": chat_id,
                media_type: media_file_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
            if reply_markup:
                data["reply_markup"] = {"inline_keyboard": reply_markup}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("result", {}).get("message_id")
                    else:
                        logger.warning(f"⚠️ Failed to send media to {chat_id}: {resp.status}")
                        return None
                        
        elif is_url:
            # Send by URL
            data = {
                "chat_id": chat_id,
                media_type: media_file_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
            if reply_markup:
                data["reply_markup"] = {"inline_keyboard": reply_markup}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("result", {}).get("message_id")
                    else:
                        logger.warning(f"⚠️ Failed to send media to {chat_id}: {resp.status}")
                        return None
                        
        else:
            # Local file path - need to upload
            file_path = MEDIA_DIR / media_file_id
            if not file_path.exists():
                logger.warning(f"Media file not found: {file_path}")
                return None

            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
            if reply_markup:
                data["reply_markup"] = {"inline_keyboard": reply_markup}

            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    form_data = aiohttp.FormData()
                    for key, value in data.items():
                        form_data.add_field(key, value)
                    form_data.add_field(media_type, f, filename=media_file_id)

                    async with session.post(url, data=form_data) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            return result.get("result", {}).get("message_id")
                        else:
                            logger.warning(f"⚠️ Failed to send media to {chat_id}: {resp.status}")
                            return None
    except Exception as e:
        logger.error(f"❌ Error sending media message: {e}")
        return None


def get_complaint_keyboard(complaint_id: int) -> list:
    """Build inline keyboard for complaint"""
    return [[
        {"text": "✅ Принять", "callback_data": f"accept_{complaint_id}"},
        {"text": "❌ Отклонить", "callback_data": f"reject_{complaint_id}"},
        {"text": "🚫 Заблокировать", "callback_data": f"block_{complaint_id}"},
    ]]


def build_complaint_text(complaint_id, uname, user_id, fio, address, description) -> str:
    """Build complaint message text"""
    return (
        f"📨 <b>Новая жалоба #{complaint_id}</b>\n\n"
        f"👤 <b>От:</b> {uname} (ID: <code>{user_id}</code>)\n"
        f"📋 <b>ФИО заявителя:</b> {fio}\n"
        f"🏠 <b>Адрес:</b> {address}\n"
        f"📝 <b>Суть жалобы:</b> {description}"
    )


async def notify_workers_about_complaint(complaint_id: int, user_id: int, fio: str, address: str,
                                          description: str, media_file_id: str | None,
                                          media_type: str | None, media_local_path: str | None):
    """Send complaint notification to admin and all registered employees"""
    db = get_db()
    
    logger.info(f"📢 Notifying workers about complaint #{complaint_id}")
    logger.info(f"   media_file_id={media_file_id}, media_type={media_type}, media_local_path={media_local_path}")

    # Get all recipients (admin + employees)
    recipients = [ADMIN_ID] if ADMIN_ID else []
    employees = db.execute("SELECT user_id FROM employees WHERE registered=1 AND user_id IS NOT NULL").fetchall()
    recipients.extend([e[0] for e in employees if e[0]])
    
    logger.info(f"   Recipients: {recipients}")

    # Get username for the complainant
    user_info = db.execute("SELECT username FROM complaints WHERE id=?", (complaint_id,)).fetchone()
    username = user_info[0] if user_info and user_info[0] else None

    # Upload media to Telegram if we have a local file
    telegram_file_id = None
    if media_local_path and media_type:
        logger.info(f"📤 Uploading media to Telegram...")
        telegram_file_id = await upload_media_to_telegram(media_type, media_local_path)
        if telegram_file_id:
            # Update DB with the real Telegram file_id
            db.execute(
                "UPDATE complaints SET media_file_id = ? WHERE id = ?",
                (telegram_file_id, complaint_id)
            )
            db.commit()
            logger.info(f"✅ Updated complaint #{complaint_id} with Telegram file_id: {telegram_file_id[:20]}...")

    uname = f"@{username}" if username else f"ID: {user_id}"
    text = build_complaint_text(complaint_id, uname, user_id, fio, address, description)
    keyboard = get_complaint_keyboard(complaint_id)

    # Use the Telegram file_id for sending to all recipients
    final_file_id = telegram_file_id if telegram_file_id else (media_file_id if media_type != "link" else None)

    msg_rows = []

    for rid in recipients:
        try:
            if final_file_id and media_type and media_type != "link":
                # Send media with file_id from Telegram
                logger.info(f"   Sending media to {rid}...")
                message_id = await send_media_message(rid, media_type, final_file_id, text, keyboard)
                if message_id:
                    msg_rows.append((complaint_id, rid, message_id))
                    logger.info(f"   ✅ Sent to {rid}, message_id={message_id}")
            elif media_file_id and media_type == "link":
                # Send text with link
                full_text = text + f"\n🔗 <b>Доказательство:</b> {media_file_id}"
                message_id = await send_telegram_message(rid, full_text, "HTML", keyboard)
                if message_id:
                    msg_rows.append((complaint_id, rid, message_id))
            else:
                # Send text only
                message_id = await send_telegram_message(rid, text, "HTML", keyboard)
                if message_id:
                    msg_rows.append((complaint_id, rid, message_id))
        except Exception as e:
            logger.warning("Could not send complaint to %s: %s", rid, e)

    # Save message IDs for later inline keyboard editing
    if msg_rows:
        db.executemany(
            "INSERT INTO complaint_messages (complaint_id, chat_id, message_id) VALUES (?,?,?)",
            msg_rows,
        )
        db.commit()

    db.close()
    logger.info(f"📨 Жалоба #{complaint_id} отправлена {len(recipients)} получателям")


async def send_notification(user_id: int, message: str):
    """Send notification to user via Telegram bot"""
    message_id = await send_telegram_message(user_id, message)
    if message_id:
        logger.info(f"✅ Notification sent to user {user_id}")


async def log_to_archive_group(
    complaint_id: int,
    action: str,  # "принята" or "отклонена"
    actor_id: int | None,
    actor_username: str | None,
    reason: str | None = None
):
    """Log complaint action to archive group (LOG_CHAT_ID) like bot does"""
    if not LOG_CHAT_ID:
        return
    
    db = get_db()
    complaint = db.execute(
        "SELECT user_id, username, fio, address, description, media_file_id, media_type FROM complaints WHERE id = ?",
        (complaint_id,)
    ).fetchone()
    
    emp = None
    if actor_id:
        emp = db.execute(
            "SELECT fio, position, area FROM employees WHERE user_id = ?",
            (actor_id,)
        ).fetchone()
    db.close()
    
    if not complaint:
        return
    
    action_emoji = "✅" if action == "принята" else "❌"
    actor_uname = f"@{actor_username}" if actor_username else (f"ID: {actor_id}" if actor_id else "Администратор")
    uname = f"@{complaint['username']}" if complaint['username'] else f"ID: {complaint['user_id']}"
    
    complaint_text = (
        f"{action_emoji} <b>Жалоба №{complaint_id} {action}</b> ({actor_uname})\n\n"
        f"👤 <b>От:</b> {uname} (ID: <code>{complaint['user_id']}</code>)\n"
        f"📋 <b>ФИО заявителя:</b> {complaint['fio']}\n"
        f"🏠 <b>Адрес:</b> {complaint['address']}\n"
        f"📝 <b>Суть жалобы:</b> {complaint['description']}"
    )
    
    if reason:
        complaint_text += f"\n📝 <b>Причина отказа:</b> {reason}"
    
    if complaint['media_type'] == 'link' and complaint['media_file_id']:
        complaint_text += f"\n🔗 <b>Фото/видео:</b> {complaint['media_file_id']}"
    
    await send_telegram_message(LOG_CHAT_ID, complaint_text)
    
    # Staff card
    if emp:
        staff_text = (
            f"🔧 <b>Карточка работника</b>\n\n"
            f"📋 ФИО: {emp['fio'] or '—'}\n"
            f"🏷 Должность: {emp['position'] or '—'}\n"
            f"📍 Участок: {emp['area'] or '—'}\n"
            f"🔗 Telegram: {actor_uname}"
        )
    else:
        staff_text = (
            f"🔧 <b>Карточка работника</b>\n\n"
            f"🔗 Telegram: {actor_uname}\n"
            f"(Администратор)"
        )
    await send_telegram_message(LOG_CHAT_ID, staff_text)


def cleanup_expired_codes():
    """Remove expired verification codes from database"""
    db = get_db()
    db.execute("DELETE FROM verification_codes WHERE expires_at < datetime('now')")
    db.commit()
    db.close()


@app.on_event("startup")
async def startup_event():
    logger.info("🌐 Web-панель запущена")
    # Cleanup expired verification codes on startup
    cleanup_expired_codes()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Web-панель остановлена")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if check_auth(request):
        role = get_user_role(request)
        if role == "employee":
            return RedirectResponse(url="/employee/complaints", status_code=302)
        elif role == "user":
            return RedirectResponse(url="/user/complaints", status_code=302)
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    else:
        return RedirectResponse(url="/login", status_code=302)


# ---------------------------------------------------------------------------
# Auth - Unified login page with role selection
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, role: str = None):
    if check_auth(request):
        if check_admin_auth(request):
            return RedirectResponse(url="/admin/complaints", status_code=302)
        elif check_employee_auth(request):
            return RedirectResponse(url="/employee/complaints", status_code=302)
        elif check_user_auth(request):
            return RedirectResponse(url="/user/complaints", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "role": role or "admin"})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    role = form.get("role", "admin").lower()

    if role not in ["admin", "employee", "user"]:
        return RedirectResponse(url="/login?error=1&role=admin", status_code=302)

    if role == "admin":
        password = form.get("password", "")
        if password == ADMIN_PASSWORD:
            logger.info("✅ Успешный вход администратора")
            response = RedirectResponse(url="/admin/dashboard", status_code=302)
            response.set_cookie("auth_token", SECRET_KEY, httponly=True, max_age=86400 * 7)
            response.set_cookie("user_role", "admin", httponly=True, max_age=86400 * 7)
            return response
        logger.warning("❌ Неудачная попытка входа администратора (неверный пароль)")
        return RedirectResponse(url="/login?error=1&role=admin", status_code=302)

    elif role == "employee":
        code = form.get("code", "").strip()

        if not code or len(code) != 6 or not code.isdigit():
            logger.warning(f"❌ Попытка входа сотрудника с неверным кодом: {code}")
            return RedirectResponse(url="/login?error=invalid_code&role=employee", status_code=302)

        db = get_db()
        verification = db.execute(
            "SELECT user_id, username FROM verification_codes WHERE code=? AND used=0 AND expires_at > datetime('now')",
            (code,)
        ).fetchone()

        if not verification:
            db.close()
            logger.warning(f"❌ Неверный или истёкший код: {code}")
            return RedirectResponse(url="/login?error=invalid_code&role=employee", status_code=302)

        user_id, username = verification

        db.execute("UPDATE verification_codes SET used=1 WHERE code=?", (code,))
        db.execute("UPDATE employees SET web_linked=1 WHERE user_id=?", (user_id,))
        db.commit()
        db.close()

        logger.info(f"✅ Успешный вход сотрудника: {username} ({user_id})")
        response = RedirectResponse(url="/employee/complaints", status_code=302)
        response.set_cookie("auth_token", SECRET_KEY, httponly=True, max_age=86400 * 7)
        response.set_cookie("user_role", "employee", httponly=True, max_age=86400 * 7)
        response.set_cookie("employee_user_id", str(user_id), httponly=True, max_age=86400 * 7)
        return response

    else:  # user
        code = form.get("code", "").strip()

        if not code or len(code) != 6 or not code.isdigit():
            logger.warning(f"❌ Попытка входа пользователя с неверным кодом: {code}")
            return RedirectResponse(url="/login?error=invalid_code&role=user", status_code=302)

        db = get_db()
        verification = db.execute(
            "SELECT user_id, username FROM verification_codes WHERE code=? AND used=0 AND expires_at > datetime('now')",
            (code,)
        ).fetchone()

        if not verification:
            db.close()
            logger.warning(f"❌ Неверный или истёкший код: {code}")
            return RedirectResponse(url="/login?error=invalid_code&role=user", status_code=302)

        user_id, username = verification

        db.execute("UPDATE verification_codes SET used=1 WHERE code=?", (code,))
        db.commit()
        db.close()

        logger.info(f"✅ Успешный вход пользователя: {username} ({user_id})")
        response = RedirectResponse(url="/user/complaints", status_code=302)
        response.set_cookie("auth_token", SECRET_KEY, httponly=True, max_age=86400 * 7)
        response.set_cookie("user_role", "user", httponly=True, max_age=86400 * 7)
        response.set_cookie("user_user_id", str(user_id), httponly=True, max_age=86400 * 7)
        return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("auth_token")
    response.delete_cookie("user_role")
    response.delete_cookie("employee_user_id")
    response.delete_cookie("user_user_id")
    return response


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    
    total = db.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM complaints WHERE status='pending'").fetchone()[0]
    accepted = db.execute("SELECT COUNT(*) FROM complaints WHERE status='accepted'").fetchone()[0]
    rejected = db.execute("SELECT COUNT(*) FROM complaints WHERE status='rejected'").fetchone()[0]
    blocked_count = db.execute("SELECT COUNT(*) FROM blocked_users").fetchone()[0]
    employees_count = db.execute("SELECT COUNT(*) FROM employees WHERE registered=1").fetchone()[0]
    
    recent = db.execute("""
        SELECT id, fio, address, description, status, created_at 
        FROM complaints ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    
    # Complaints by date (last 30 days)
    complaints_by_date = db.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM complaints
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """).fetchall()
    
    db.close()
    
    # Format data for chart
    dates = [row[0] for row in complaints_by_date]
    counts = [row[1] for row in complaints_by_date]
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "stats": {
            "total": total,
            "pending": pending,
            "accepted": accepted,
            "rejected": rejected,
            "blocked": blocked_count,
            "employees": employees_count,
        },
        "recent_complaints": recent,
        "chart_dates": dates,
        "chart_counts": counts,
    })

@app.get("/admin/complaints", response_class=HTMLResponse)
async def admin_complaints_list(
    request: Request,
    status: str = None,
    search: str = None,
    page: int = 1,
):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    per_page = 20
    offset = (page - 1) * per_page
    
    query = "SELECT * FROM complaints WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    if search:
        query += " AND (fio LIKE ? OR address LIKE ? OR description LIKE ?)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = db.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    complaints = db.execute(query, params).fetchall()
    
    db.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse("admin/complaints.html", {
        "request": request,
        "complaints": complaints,
        "current_status": status,
        "search": search or "",
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@app.get("/admin/complaints/{complaint_id}", response_class=HTMLResponse)
async def admin_complaint_detail(request: Request, complaint_id: int):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    complaint = db.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    
    if not complaint:
        db.close()
        raise HTTPException(status_code=404, detail="Жалоба не найдена")
    
    accepted_by_info = None
    if complaint["accepted_by"]:
        accepted_by_info = db.execute(
            "SELECT fio, position FROM employees WHERE user_id = ?",
            (complaint["accepted_by"],)
        ).fetchone()
    
    db.close()
    
    return templates.TemplateResponse("admin/complaint_detail.html", {
        "request": request,
        "complaint": complaint,
        "accepted_by_info": accepted_by_info,
    })


@app.post("/admin/complaints/{complaint_id}/accept")
async def admin_accept_complaint(request: Request, complaint_id: int):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    complaint = db.execute("SELECT user_id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    db.execute(
        "UPDATE complaints SET status = 'accepted' WHERE id = ? AND status = 'pending'",
        (complaint_id,)
    )
    db.commit()
    db.close()
    
    if complaint:
        # Detailed notification like bot sends
        notification = (
            f"✅ <b>Ваша жалоба №{complaint_id} принята!</b>\n\n"
            f"Работник будет направлен для устранения проблемы.\n\n"
            f"💡 После выполнения работы вы сможете оценить качество обслуживания."
        )
        await send_notification(complaint["user_id"], notification)
        # Log to archive group
        await log_to_archive_group(complaint_id, "принята", None, None)
    
    return RedirectResponse(url=f"/admin/complaints/{complaint_id}", status_code=302)


@app.post("/admin/complaints/{complaint_id}/reject")
async def admin_reject_complaint(request: Request, complaint_id: int):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    form = await request.form()
    reason = form.get("reason", "").strip()
    
    db = get_db()
    complaint = db.execute("SELECT user_id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    db.execute(
        "UPDATE complaints SET status = 'rejected', rejection_reason = ? WHERE id = ? AND status = 'pending'",
        (reason if reason else None, complaint_id)
    )
    db.commit()
    db.close()
    
    if complaint:
        msg = f"❌ Ваша жалоба №{complaint_id} отклонена."
        if reason:
            msg += f"\n\n📝 <b>Причина:</b> {reason}"
        await send_notification(complaint["user_id"], msg)
        # Log to archive group
        await log_to_archive_group(complaint_id, "отклонена", None, None, reason)
    
    return RedirectResponse(url=f"/admin/complaints/{complaint_id}", status_code=302)


@app.get("/admin/employees", response_class=HTMLResponse)
async def admin_employees_list(request: Request):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    employees = db.execute("""
        SELECT * FROM employees ORDER BY registered DESC, added_at DESC
    """).fetchall()
    db.close()
    
    return templates.TemplateResponse("admin/employees.html", {
        "request": request,
        "employees": employees,
    })


@app.post("/admin/employees/add")
async def admin_add_employee(request: Request):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    form = await request.form()
    username = form.get("username", "").lstrip("@").lower().strip()
    
    if not username:
        return RedirectResponse(url="/admin/employees?error=empty", status_code=302)
    
    db = get_db()
    existing = db.execute("SELECT 1 FROM employees WHERE username = ?", (username,)).fetchone()
    if existing:
        db.close()
        return RedirectResponse(url="/admin/employees?error=exists", status_code=302)
    
    db.execute("INSERT INTO employees (username) VALUES (?)", (username,))
    db.commit()
    db.close()
    return RedirectResponse(url="/admin/employees?success=1", status_code=302)


@app.post("/admin/employees/delete/{username}")
async def admin_delete_employee(request: Request, username: str):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    db.execute("DELETE FROM employees WHERE username = ?", (username,))
    db.commit()
    db.close()
    return RedirectResponse(url="/admin/employees", status_code=302)


@app.get("/admin/blocked", response_class=HTMLResponse)
async def admin_blocked_list(request: Request):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    blocked = db.execute("SELECT * FROM blocked_users ORDER BY blocked_at DESC").fetchall()
    db.close()
    
    return templates.TemplateResponse("admin/blocked.html", {
        "request": request,
        "blocked_users": blocked,
    })


@app.post("/admin/blocked/unblock/{user_id}")
async def admin_unblock_user(request: Request, user_id: int):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    db.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
    db.commit()
    db.close()
    return RedirectResponse(url="/admin/blocked", status_code=302)


@app.get("/admin/ratings", response_class=HTMLResponse)
async def admin_ratings(request: Request):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    
    employees_stats = db.execute("""
        SELECT 
            e.user_id,
            e.username,
            e.fio,
            e.position,
            e.area,
            COUNT(c.id) as total_accepted,
            AVG(c.rating) as avg_rating,
            COUNT(CASE WHEN c.rating IS NOT NULL THEN 1 END) as rated_count
        FROM employees e
        LEFT JOIN complaints c ON e.user_id = c.accepted_by
        WHERE e.registered = 1
        GROUP BY e.user_id
        ORDER BY CASE WHEN avg_rating IS NULL THEN 1 ELSE 0 END, avg_rating DESC, total_accepted DESC
    """).fetchall()
    
    recent_reviews = db.execute("""
        SELECT 
            c.id,
            c.rating,
            c.review,
            c.rated_at,
            c.user_id,
            c.username as user_username,
            e.fio as employee_fio,
            e.position
        FROM complaints c
        LEFT JOIN employees e ON c.accepted_by = e.user_id
        WHERE c.rating IS NOT NULL
        ORDER BY c.rated_at DESC
        LIMIT 10
    """).fetchall()
    
    db.close()
    
    return templates.TemplateResponse("admin/ratings.html", {
        "request": request,
        "employees_stats": employees_stats,
        "recent_reviews": recent_reviews,
    })


# ---------------------------------------------------------------------------
# Employee Panel
# ---------------------------------------------------------------------------

@app.get("/employee/complaints", response_class=HTMLResponse)
async def employee_complaints_list(
    request: Request,
    status: str = None,
    search: str = None,
    page: int = 1,
):
    if not check_employee_auth(request):
        return RedirectResponse(url="/login?role=employee", status_code=302)
    
    db = get_db()
    per_page = 20
    offset = (page - 1) * per_page
    
    query = "SELECT * FROM complaints WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    if search:
        query += " AND (fio LIKE ? OR address LIKE ? OR description LIKE ?)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])
    
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = db.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    complaints = db.execute(query, params).fetchall()
    
    db.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse("employee/complaints.html", {
        "request": request,
        "complaints": complaints,
        "current_status": status,
        "search": search or "",
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@app.get("/employee/complaints/{complaint_id}", response_class=HTMLResponse)
async def employee_complaint_detail(request: Request, complaint_id: int):
    if not check_employee_auth(request):
        return RedirectResponse(url="/login?role=employee", status_code=302)
    
    db = get_db()
    complaint = db.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    
    if not complaint:
        db.close()
        raise HTTPException(status_code=404, detail="Жалоба не найдена")
    
    db.close()
    
    return templates.TemplateResponse("employee/complaint_detail.html", {
        "request": request,
        "complaint": complaint,
    })


@app.post("/employee/complaints/{complaint_id}/accept")
async def employee_accept_complaint(request: Request, complaint_id: int):
    if not check_employee_auth(request):
        return RedirectResponse(url="/login?role=employee", status_code=302)
    
    employee_user_id = request.cookies.get("employee_user_id")
    if not employee_user_id:
        return RedirectResponse(url="/login?role=employee", status_code=302)
    
    employee_user_id = int(employee_user_id)
    
    db = get_db()
    complaint = db.execute("SELECT user_id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    emp = db.execute(
        "SELECT fio, position, area, username FROM employees WHERE user_id = ?",
        (employee_user_id,)
    ).fetchone()
    db.execute(
        "UPDATE complaints SET status = 'accepted', accepted_by = ? WHERE id = ? AND status = 'pending'",
        (employee_user_id, complaint_id)
    )
    db.commit()
    db.close()
    
    if complaint:
        # Detailed notification with worker info like bot sends
        if emp:
            notification = (
                f"✅ <b>Ваша жалоба №{complaint_id} принята!</b>\n\n"
                f"Работник будет направлен для устранения проблемы.\n\n"
                f"👷 <b>Информация о работнике:</b>\n"
                f"📋 ФИО: {emp['fio'] or '—'}\n"
                f"🏷 Должность: {emp['position'] or '—'}\n"
                f"📍 Участок: {emp['area'] or '—'}\n\n"
                f"💡 После выполнения работы вы сможете оценить качество обслуживания."
            )
        else:
            notification = (
                f"✅ <b>Ваша жалоба №{complaint_id} принята!</b>\n\n"
                f"Работник будет направлен для устранения проблемы.\n\n"
                f"💡 После выполнения работы вы сможете оценить качество обслуживания."
            )
        await send_notification(complaint["user_id"], notification)
        # Log to archive group
        await log_to_archive_group(
            complaint_id, "принята", 
            employee_user_id, 
            emp['username'] if emp else None
        )
    
    return RedirectResponse(url=f"/employee/complaints/{complaint_id}", status_code=302)


@app.post("/employee/complaints/{complaint_id}/reject")
async def employee_reject_complaint(request: Request, complaint_id: int):
    if not check_employee_auth(request):
        return RedirectResponse(url="/login?role=employee", status_code=302)
    
    employee_user_id = request.cookies.get("employee_user_id")
    employee_username = None
    if employee_user_id:
        db_temp = get_db()
        emp = db_temp.execute("SELECT username FROM employees WHERE user_id = ?", (employee_user_id,)).fetchone()
        employee_username = emp['username'] if emp else None
        db_temp.close()
    
    form = await request.form()
    reason = form.get("reason", "").strip()
    
    db = get_db()
    complaint = db.execute("SELECT user_id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    db.execute(
        "UPDATE complaints SET status = 'rejected', rejection_reason = ? WHERE id = ? AND status = 'pending'",
        (reason if reason else None, complaint_id)
    )
    db.commit()
    db.close()
    
    if complaint:
        msg = f"❌ Ваша жалоба №{complaint_id} отклонена."
        if reason:
            msg += f"\n\n📝 <b>Причина:</b> {reason}"
        await send_notification(complaint["user_id"], msg)
        # Log to archive group
        await log_to_archive_group(
            complaint_id, "отклонена",
            int(employee_user_id) if employee_user_id else None,
            employee_username,
            reason
        )
    
    return RedirectResponse(url=f"/employee/complaints/{complaint_id}", status_code=302)


@app.get("/employee/ratings", response_class=HTMLResponse)
async def employee_ratings(request: Request):
    if not check_employee_auth(request):
        return RedirectResponse(url="/login?role=employee", status_code=302)
    
    db = get_db()
    
    employees_stats = db.execute("""
        SELECT 
            e.user_id,
            e.username,
            e.fio,
            e.position,
            e.area,
            COUNT(c.id) as total_accepted,
            AVG(c.rating) as avg_rating,
            COUNT(CASE WHEN c.rating IS NOT NULL THEN 1 END) as rated_count
        FROM employees e
        LEFT JOIN complaints c ON e.user_id = c.accepted_by
        WHERE e.registered = 1
        GROUP BY e.user_id
        ORDER BY CASE WHEN avg_rating IS NULL THEN 1 ELSE 0 END, avg_rating DESC, total_accepted DESC
    """).fetchall()
    
    recent_reviews = db.execute("""
        SELECT 
            c.id,
            c.rating,
            c.review,
            c.rated_at,
            c.user_id,
            c.username as user_username,
            e.fio as employee_fio,
            e.position
        FROM complaints c
        LEFT JOIN employees e ON c.accepted_by = e.user_id
        WHERE c.rating IS NOT NULL
        ORDER BY c.rated_at DESC
        LIMIT 10
    """).fetchall()
    
    db.close()
    
    return templates.TemplateResponse("employee/ratings.html", {
        "request": request,
        "employees_stats": employees_stats,
        "recent_reviews": recent_reviews,
    })


# ---------------------------------------------------------------------------
# User Panel
# ---------------------------------------------------------------------------

@app.get("/user/complaints", response_class=HTMLResponse)
async def user_complaints(request: Request):
    if not check_user_auth(request):
        return RedirectResponse(url="/login?role=user", status_code=302)

    user_id = int(request.cookies.get("user_user_id", "0"))
    db = get_db()
    
    complaints = db.execute("""
        SELECT id, fio, address, description, status, rating, review, created_at, accepted_by
        FROM complaints 
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    
    # Get employee info for accepted complaints
    complaints_with_emp = []
    for c in complaints:
        emp_info = None
        if c["accepted_by"]:
            emp_info = db.execute(
                "SELECT fio, position FROM employees WHERE user_id = ?",
                (c["accepted_by"],)
            ).fetchone()
        complaints_with_emp.append({**dict(c), "employee_info": emp_info})
    
    db.close()
    
    return templates.TemplateResponse("user/complaints.html", {
        "request": request,
        "complaints": complaints_with_emp,
    })


@app.get("/user/complaints/new", response_class=HTMLResponse)
async def new_complaint_form(request: Request):
    if not check_user_auth(request):
        return RedirectResponse(url="/login?role=user", status_code=302)
    
    return templates.TemplateResponse("user/complaint_form.html", {
        "request": request,
    })


@app.post("/user/complaints/new")
async def submit_complaint(request: Request):
    if not check_user_auth(request):
        return RedirectResponse(url="/login?role=user", status_code=302)

    user_id = int(request.cookies.get("user_user_id", "0"))
    form = await request.form()

    fio = form.get("fio", "").strip()
    address = form.get("address", "").strip()
    description = form.get("description", "").strip()

    if not fio or not address or not description:
        return templates.TemplateResponse("user/complaint_form.html", {
            "request": request,
            "error": "Все поля обязательны для заполнения",
        })

    # Handle media upload
    media_file = form.get("media")
    media_link = form.get("media_link", "").strip()

    media_file_id = None
    media_type = None
    media_local_path = None

    if media_file and hasattr(media_file, 'filename') and media_file.filename:
        # Upload file
        import uuid
        from pathlib import Path

        ext = Path(media_file.filename).suffix.lower()
        if not ext:
            ext = ".bin"

        filename = f"{user_id}_{uuid.uuid4().hex[:10]}{ext}"
        local_path = MEDIA_DIR / filename

        # Determine media type
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            media_type = "photo"
        elif ext in ['.mp4', '.avi', '.mov', '.webm']:
            media_type = "video"
        else:
            media_type = "document"

        # Save file
        content = await media_file.read()
        with open(local_path, 'wb') as f:
            f.write(content)

        media_local_path = str(local_path)
        media_file_id = filename  # Store filename for reference

    elif media_link:
        # Use link
        if media_link.startswith("http://") or media_link.startswith("https://"):
            media_file_id = media_link
            media_type = "link"

    # Save complaint
    db = get_db()
    username = None  # Will be filled if linked
    cursor = db.execute(
        """INSERT INTO complaints (user_id, username, fio, address, description, media_file_id, media_type, media_local_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, username, fio, address, description, media_file_id, media_type, media_local_path)
    )
    complaint_id = cursor.lastrowid
    db.commit()
    db.close()

    logger.info(f"📨 Новая жалоба #{complaint_id} от пользователя {user_id} (веб-панель)")
    logger.info(f"   Media: file_id={media_file_id}, type={media_type}, local_path={media_local_path}")

    # Notify workers via Telegram
    await notify_workers_about_complaint(
        complaint_id, user_id, fio, address, description,
        media_file_id, media_type, media_local_path
    )

    return RedirectResponse(url=f"/user/complaints/{complaint_id}", status_code=302)


@app.get("/user/complaints/{complaint_id}", response_class=HTMLResponse)
async def user_complaint_detail(request: Request, complaint_id: int):
    if not check_user_auth(request):
        return RedirectResponse(url="/login?role=user", status_code=302)
    
    user_id = int(request.cookies.get("user_user_id", "0"))
    
    db = get_db()
    complaint = db.execute(
        "SELECT * FROM complaints WHERE id = ? AND user_id = ?",
        (complaint_id, user_id)
    ).fetchone()
    
    if not complaint:
        db.close()
        raise HTTPException(status_code=404, detail="Жалоба не найдена")
    
    # Get employee info if accepted
    emp_info = None
    if complaint["accepted_by"]:
        emp_info = db.execute(
            "SELECT fio, position, area FROM employees WHERE user_id = ?",
            (complaint["accepted_by"],)
        ).fetchone()
    
    db.close()
    
    return templates.TemplateResponse("user/complaint_detail.html", {
        "request": request,
        "complaint": complaint,
        "employee_info": emp_info,
    })


@app.get("/user/complaints/{complaint_id}/rate", response_class=HTMLResponse)
async def rate_complaint_form(request: Request, complaint_id: int):
    if not check_user_auth(request):
        return RedirectResponse(url="/login?role=user", status_code=302)
    
    user_id = int(request.cookies.get("user_user_id", "0"))
    
    db = get_db()
    complaint = db.execute(
        "SELECT * FROM complaints WHERE id = ? AND user_id = ? AND status = 'accepted' AND rating IS NULL",
        (complaint_id, user_id)
    ).fetchone()
    
    if not complaint:
        db.close()
        return RedirectResponse(url=f"/user/complaints/{complaint_id}", status_code=302)
    
    db.close()
    
    return templates.TemplateResponse("user/rate.html", {
        "request": request,
        "complaint_id": complaint_id,
    })


@app.post("/user/complaints/{complaint_id}/rate")
async def submit_rating(request: Request, complaint_id: int):
    if not check_user_auth(request):
        return RedirectResponse(url="/login?role=user", status_code=302)
    
    user_id = int(request.cookies.get("user_user_id", "0"))
    form = await request.form()
    
    try:
        rating = int(form.get("rating", "0"))
        if not 1 <= rating <= 5:
            raise ValueError()
    except ValueError:
        return templates.TemplateResponse("user/rate.html", {
            "request": request,
            "complaint_id": complaint_id,
            "error": "Оценка должна быть от 1 до 5",
        })
    
    review = form.get("review", "").strip()
    
    db = get_db()
    # Verify complaint belongs to user and is accepted without rating
    complaint = db.execute(
        "SELECT * FROM complaints WHERE id = ? AND user_id = ? AND status = 'accepted' AND rating IS NULL",
        (complaint_id, user_id)
    ).fetchone()
    
    if not complaint:
        db.close()
        return RedirectResponse(url=f"/user/complaints/{complaint_id}", status_code=302)
    
    db.execute(
        "UPDATE complaints SET rating = ?, review = ?, rated_at = datetime('now') WHERE id = ?",
        (rating, review if review else None, complaint_id)
    )
    db.commit()
    db.close()
    
    logger.info(f"⭐ Жалоба #{complaint_id} оценена на {rating} звезд пользователем {user_id}")
    
    return RedirectResponse(url="/user/complaints", status_code=302)


# ---------------------------------------------------------------------------
# Media serving
# ---------------------------------------------------------------------------

@app.get("/media/{filename}")
async def serve_media(request: Request, filename: str):
    if not check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    file_path = MEDIA_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    if not str(file_path.resolve()).startswith(str(MEDIA_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return FileResponse(file_path)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def api_stats(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    db = get_db()
    stats = {
        "total": db.execute("SELECT COUNT(*) FROM complaints").fetchone()[0],
        "pending": db.execute("SELECT COUNT(*) FROM complaints WHERE status='pending'").fetchone()[0],
        "accepted": db.execute("SELECT COUNT(*) FROM complaints WHERE status='accepted'").fetchone()[0],
        "rejected": db.execute("SELECT COUNT(*) FROM complaints WHERE status='rejected'").fetchone()[0],
    }
    db.close()
    return stats


# ---------------------------------------------------------------------------
# Account linking - redirect to login (employee login handles codes)
# ---------------------------------------------------------------------------

@app.get("/link_account")
async def link_account_redirect(request: Request):
    """Redirect to employee login - it handles verification codes"""
    return RedirectResponse(url="/login?role=employee", status_code=302)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
