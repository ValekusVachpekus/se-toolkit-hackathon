# Copyright (C) 2026 Shchetkov Ilia
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from datetime import datetime
import aiohttp
import os

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


async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Send message via Telegram bot API"""
    if not BOT_TOKEN:
        logger.warning("⚠️ BOT_TOKEN not configured")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": chat_id, 
                "text": text,
                "parse_mode": parse_mode
            }) as resp:
                if resp.status == 200:
                    return True
                else:
                    logger.warning(f"⚠️ Failed to send message to {chat_id}: {resp.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}")
        return False


async def send_notification(user_id: int, message: str):
    """Send notification to user via Telegram bot"""
    if await send_telegram_message(user_id, message):
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
        import os
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
