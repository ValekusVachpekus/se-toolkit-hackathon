from fastapi import HTTPException, Request

from web.config import SECRET_KEY


def check_auth(request: Request) -> bool:
    token = request.cookies.get("auth_token")
    return token == SECRET_KEY


def get_user_role(request: Request) -> str:
    """Get user role from cookie: 'admin' or 'employee'"""
    return request.cookies.get("user_role", "admin")


def check_admin_auth(request: Request) -> bool:
    """Check if user is authenticated as admin"""
    return check_auth(request) and get_user_role(request) == "admin"


def check_employee_auth(request: Request) -> bool:
    """Check if user is authenticated as employee"""
    return check_auth(request) and get_user_role(request) == "employee"


def require_auth(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return True
