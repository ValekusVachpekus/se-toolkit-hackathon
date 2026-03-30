from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.auth import check_auth, check_admin_auth, check_employee_auth, get_user_role
from web.config import ADMIN_PASSWORD, MEDIA_DIR, SECRET_KEY
from web.database import get_db
from web.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="ЖКХ Панель")

templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.on_event("startup")
async def startup_event():
    logger.info("🌐 Web-панель запущена")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Web-панель остановлена")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if check_auth(request):
        return RedirectResponse(url="/admin/complaints", status_code=302)
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
        else:
            return RedirectResponse(url="/employee/complaints", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "role": role or "admin"})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    role = form.get("role", "admin").lower()
    
    if role not in ["admin", "employee"]:
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
    
    else:  # employee
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
        return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("auth_token")
    response.delete_cookie("user_role")
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
    
    db.close()
    
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
    db.execute(
        "UPDATE complaints SET status = 'accepted' WHERE id = ? AND status = 'pending'",
        (complaint_id,)
    )
    db.commit()
    db.close()
    return RedirectResponse(url=f"/admin/complaints/{complaint_id}", status_code=302)


@app.post("/admin/complaints/{complaint_id}/reject")
async def admin_reject_complaint(request: Request, complaint_id: int):
    if not check_admin_auth(request):
        return RedirectResponse(url="/login?role=admin", status_code=302)
    
    db = get_db()
    db.execute(
        "UPDATE complaints SET status = 'rejected' WHERE id = ? AND status = 'pending'",
        (complaint_id,)
    )
    db.commit()
    db.close()
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
# Account linking (redirect to login after)
# ---------------------------------------------------------------------------

@app.get("/link_account", response_class=HTMLResponse)
async def link_account_get(request: Request):
    return templates.TemplateResponse("link_account.html", {"request": request})


@app.post("/link_account")
async def link_account_post(request: Request):
    form = await request.form()
    code = form.get("code", "").strip()
    
    if not code or len(code) != 6 or not code.isdigit():
        return templates.TemplateResponse("link_account.html", {
            "request": request,
            "error": "Код должен содержать 6 цифр"
        })
    
    db = get_db()
    
    verification = db.execute(
        "SELECT user_id, username FROM verification_codes WHERE code=? AND used=0 AND expires_at > datetime('now')",
        (code,)
    ).fetchone()
    
    if not verification:
        db.close()
        return templates.TemplateResponse("link_account.html", {
            "request": request,
            "error": "Неверный или истёкший код"
        })
    
    user_id, username = verification
    
    db.execute("UPDATE verification_codes SET used=1 WHERE code=?", (code,))
    db.execute(
        "UPDATE employees SET web_linked=1 WHERE user_id=?",
        (user_id,)
    )
    db.commit()
    db.close()
    
    logger.info(f"🔗 Аккаунт {username} ({user_id}) связан с веб-панелью")
    
    response = RedirectResponse(url="/login?role=employee", status_code=302)
    response.set_cookie("auth_token", SECRET_KEY, httponly=True, max_age=86400 * 7)
    response.set_cookie("user_role", "employee", httponly=True, max_age=86400 * 7)
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
