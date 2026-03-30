import aiosqlite

from bot.config import ADMIN_ID, DB_PATH


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                username      TEXT,
                fio           TEXT NOT NULL,
                address       TEXT NOT NULL,
                description   TEXT NOT NULL,
                media_file_id TEXT,
                media_type    TEXT,
                media_local_path TEXT,
                status        TEXT DEFAULT 'pending',
                accepted_by   INTEGER,
                rating        INTEGER,
                review        TEXT,
                rated_at      TIMESTAMP,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                user_id    INTEGER,
                username   TEXT UNIQUE NOT NULL,
                fio        TEXT,
                position   TEXT,
                area       TEXT,
                registered INTEGER DEFAULT 0,
                added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaint_messages (
                complaint_id INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                message_id   INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                code       TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                username   TEXT,
                used       INTEGER DEFAULT 0,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        # Migrations for existing databases
        for col_sql in [
            "ALTER TABLE complaints ADD COLUMN address TEXT NOT NULL DEFAULT '—'",
            "ALTER TABLE complaints ADD COLUMN accepted_by INTEGER",
            "ALTER TABLE complaints ADD COLUMN media_local_path TEXT",
            "ALTER TABLE complaints ADD COLUMN rating INTEGER",
            "ALTER TABLE complaints ADD COLUMN review TEXT",
            "ALTER TABLE complaints ADD COLUMN rated_at TIMESTAMP",
            "ALTER TABLE complaints ADD COLUMN rejection_reason TEXT",
            "ALTER TABLE employees ADD COLUMN web_linked INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass
        await db.commit()


async def is_blocked(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone() is not None


async def is_registered_employee(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM employees WHERE user_id=? AND registered=1", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def is_staff(user_id: int) -> bool:
    return user_id == ADMIN_ID or await is_registered_employee(user_id)


async def get_all_recipient_ids(db) -> list[int]:
    """Admin + all registered employees."""
    ids = [ADMIN_ID]
    async with db.execute("SELECT user_id FROM employees WHERE registered=1 AND user_id IS NOT NULL") as cur:
        rows = await cur.fetchall()
    ids.extend(r[0] for r in rows if r[0])
    return ids
