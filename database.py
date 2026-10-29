"""
FocusFlow Database Module (Turso Cloud DB / LibSQL Version with Multi-User & OTP Auth)
Connects to Turso distributed LibSQL cloud database for real-time synchronization.
"""
import os
import json
import sqlite3
import uuid
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

try:
    import libsql_experimental as libsql
except ImportError:
    libsql = None


def load_dotenv():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

# 優先載入本地 .env（本地開發使用，Render 上則直接讀取 Render 後台設定的環境變數）
load_dotenv()

# 完全由系統環境變數取得，不再寫死任何預設金鑰
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "focusflow.db")

_client = None

def _sqlite_execute(sql, params=None):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql, list(params) if params else [])
        if sql.strip().lower().startswith("select") or sql.strip().lower().startswith("pragma"):
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
        conn.commit()
        result = type("SQLiteResult", (), {"last_insert_rowid": cur.lastrowid, "rowcount": cur.rowcount})()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_client():
    """Returns the active database client or a SQLite fallback marker."""
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("TURSO_DATABASE_URL", TURSO_DATABASE_URL)
    token = os.environ.get("TURSO_AUTH_TOKEN", TURSO_AUTH_TOKEN)

    # 若未提供 Turso 連線資訊，自動退回本地 SQLite
    if not url or not token or libsql is None:
        print("⚠️ 未檢測到完整的 TURSO 環境變數，使用本地 SQLite 資料庫")
        _client = "sqlite"
        return _client
  
    try:
        _client = libsql.connect(url, auth_token=token)
        print("✅ 成功連線至 Turso 雲端 LibSQL 資料庫！")
        return _client
    except Exception as e:
        print(f"⚠️ Turso 連線失敗，退回本地 SQLite: {e}")
        _client = "sqlite"
        return _client

get_connection = get_client

def execute_query(sql, params=None):
    """Executes a SELECT query and returns rows as list of dicts."""
    client = get_client()
    if client == "sqlite":
        return _sqlite_execute(sql, params)

    try:
        res = client.execute(sql, list(params) if params else [])
        cols = res.columns
        return [dict(zip(cols, row)) for row in res.rows]
    except Exception as e:
        print(f"Turso query error, fallback to sqlite: {e}")
        return _sqlite_execute(sql, params)

def execute_mutate(sql, params=None):
    """Executes an INSERT, UPDATE, or DELETE and returns the ResultSet."""
    client = get_client()
    if client == "sqlite":
        return _sqlite_execute(sql, params)

    try:
        return client.execute(sql, list(params) if params else [])
    except Exception as e:
        print(f"Turso mutate error, fallback to sqlite: {e}")
        return _sqlite_execute(sql, params)

def init_db():
    """Initializes tables in Turso Cloud DB / SQLite and configures multi-user isolation."""
    # 1. 建立靜態任務表
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        category TEXT DEFAULT '報告',
        status TEXT DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        priority TEXT DEFAULT 'medium',
        due_date TEXT,
        description TEXT,
        checklist_json TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 2. 建立靈感庫表
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT DEFAULT '',
        color TEXT DEFAULT '#fef3c7',
        is_starred INTEGER DEFAULT 0,
        converted_to_task_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 3. 建立業務會談紀錄表
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS business_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        raw_transcript TEXT NOT NULL,
        summary TEXT,
        action_items_json TEXT DEFAULT '[]',
        event_time TEXT,
        duration_minutes INTEGER DEFAULT 60,
        calendar_status TEXT DEFAULT 'unpushed',
        google_calendar_url TEXT,
        client_name TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 4. 建立任務分類表
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS task_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        color TEXT DEFAULT 'indigo',
        created_at TEXT NOT NULL
    );
    """)

    # 5. 使用者表 (Users)
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 6. Email 動態驗證碼表 (Email OTPs) - 雲端 Turso 專用
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS email_otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # 7. 使用者 Session 表 (Sessions)
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 自動遷移歷史資料表結構
    for tbl in ['tasks', 'ideas', 'business_logs', 'task_categories']:
        try:
            execute_mutate(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER;")
        except Exception:
            pass

    # 檢查預設類別
    cats = execute_query("SELECT COUNT(*) as count FROM task_categories;")
    cat_count = cats[0]['count'] if cats else 0
    if cat_count == 0:
        seed_default_categories(user_id=None)

def seed_default_categories(user_id=None):
    """Inserts default categories into DB for a user or global fallback."""
    default_cats = [
        ('報告', 'indigo'),
        ('簡報', 'rose'),
        ('資料分析', 'amber'),
        ('系統測試', 'emerald'),
        ('其他', 'slate')
    ]
    now = datetime.now().isoformat()
    for name, color in default_cats:
        if user_id:
            existing = execute_query(
                "SELECT id FROM task_categories WHERE (user_id = ? OR user_id IS NULL) AND name = ? LIMIT 1;",
                [user_id, name]
            )
        else:
            existing = execute_query(
                "SELECT id FROM task_categories WHERE name = ? LIMIT 1;",
                [name]
            )
        if not existing:
            try:
                execute_mutate(
                    "INSERT INTO task_categories (user_id, name, color, created_at) VALUES (?, ?, ?, ?);",
                    [user_id, name, color, now]
                )
            except Exception:
                pass

def generate_and_save_otp(email):
    """Generates a 6-digit OTP, stores it in Turso email_otps table, and sends via SMTP."""
    email = email.strip().lower()
    code = f"{random.randint(100000, 999999)}"
    now = datetime.now()
    expires_at = (now + timedelta(minutes=10)).isoformat()
    now_str = now.isoformat()

    # 1. 統一使用 execute_mutate 寫入 Turso 的 email_otps 表
    try:
        execute_mutate("""
            INSERT INTO email_otps (email, code, expires_at, used, created_at)
            VALUES (?, ?, ?, 0, ?);
        """, [email, code, expires_at, now_str])
        print(f" OTP 已成功寫入 Turso 雲端資料庫 email_otps: {email} -> {code}")
    except Exception as db_err:
        print(f"❌ 寫入 Turso 失敗: {db_err}")

    # 2. 嘗試 SMTP 發信
    email_sent = False
    try:
        ok, msg = send_otp_email(email, code)
        email_sent = ok and "已成功發送" in msg
    except Exception as e:
        print(f"⚠️ SMTP 發送失敗或未設定: {e}")
        email_sent = False

    # 3. 回傳 dev_code 給前端彈窗/提示帶入
    return {
        "success": True,
        "dev_code": code,
        "message": "驗證碼已寄送至您的信箱！" if email_sent else f"【測試模式】動態驗證碼為：{code}"
    }

def send_otp_email(to_email: str, code: str):
    """Sends OTP code via SMTP if configured; otherwise logs to console."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user or "noreply@focusflow.com")
    smtp_tls = os.environ.get("SMTP_TLS", "true").lower() == "true"

    if smtp_host and smtp_user and smtp_pass:
        try:
            subject = f"【FocusFlow】您的登入動態確認碼：{code}"
            html_content = f"""
            <div style="font-family: sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 16px;">
                <h2 style="color: #4f46e5;">⚡ FocusFlow 智慧工作追蹤</h2>
                <p>請於登入畫面輸入以下 6 位數動態確認碼：</p>
                <div style="background: #f8fafc; border: 1px dashed #cbd5e1; padding: 20px; text-align: center; margin: 24px 0;">
                    <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #1e293b;">{code}</span>
                </div>
                <p style="color: #64748b; font-size: 13px;">有效期限 10 分鐘。</p>
            </div>
            """
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                if smtp_tls:
                    server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_email], msg.as_string())
            server.quit()
            return True, "動態確認碼已成功發送至您的 Email 信箱"
        except Exception as e:
            print(f"⚠️ SMTP 錯誤: {e}")
            return False, f"SMTP 錯誤: {e}"
    else:
        return False, "未設定 SMTP"

def verify_otp_and_login(email: str, code: str):
    """Verifies the OTP code for an email and issues a 30-day session token."""
    email = email.strip().lower()
    code = str(code).strip()
    now_iso = datetime.now().isoformat()

    # 統一由 Turso email_otps 查詢
    rows = execute_query(
        "SELECT * FROM email_otps WHERE email = ? AND code = ? AND used = 0 AND expires_at >= ? ORDER BY id DESC LIMIT 1;",
        [email, code, now_iso]
    )
    if not rows:
        return {"success": False, "error": "確認碼錯誤或已過期，請重新索取！"}

    otp_id = rows[0]['id']
    execute_mutate("UPDATE email_otps SET used = 1 WHERE id = ?;", [otp_id])

    # 取得或建立使用者
    user = get_or_create_user(email)

    # 建立 Session Token
    token = uuid.uuid4().hex + uuid.uuid4().hex
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()
    created_at = datetime.now().isoformat()

    execute_mutate(
        "INSERT INTO sessions (token, user_id, email, expires_at, created_at) VALUES (?, ?, ?, ?, ?);",
        [token, user['id'], email, expires_at, created_at]
    )

    return {
        "success": True,
        "token": token,
        "user": user
    }

def get_or_create_user(email: str):
    email = email.strip().lower()
    users = execute_query("SELECT * FROM users WHERE email = ? LIMIT 1;", [email])
    if users:
        return users[0]

    now = datetime.now().isoformat()
    name = email.split('@')[0]
    res = execute_mutate("INSERT INTO users (email, name, created_at) VALUES (?, ?, ?);", [email, name, now])
    
    # 支援 Turso 及 SQLite 的回傳格式相容
    user_id = getattr(res, "last_insert_rowid", None)
    if user_id is None:
        created_user = execute_query("SELECT id FROM users WHERE email = ? LIMIT 1;", [email])
        user_id = created_user[0]['id'] if created_user else 1

    seed_default_categories(user_id=user_id)
    return {"id": user_id, "email": email, "name": name, "created_at": now}

def get_user_by_token(token: str):
    if not token:
        return None
    token = token.strip()
    now_iso = datetime.now().isoformat()

    sessions = execute_query(
        "SELECT * FROM sessions WHERE token = ? AND expires_at >= ? LIMIT 1;",
        [token, now_iso]
    )
    if not sessions:
        return None

    user_id = sessions[0]['user_id']
    users = execute_query("SELECT * FROM users WHERE id = ? LIMIT 1;", [user_id])
    return users[0] if users else None

def delete_session(token: str):
    if token:
        execute_mutate("DELETE FROM sessions WHERE token = ?;", [token.strip()])
    return True

# ----------------- User-Scoped Tasks CRUD -----------------
def get_all_tasks(user_id=None):
    if user_id:
        rows = execute_query("""
        SELECT * FROM tasks 
        WHERE user_id = ? OR user_id IS NULL
        ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, due_date ASC;
        """, [user_id])
    else:
        rows = execute_query("""
        SELECT * FROM tasks 
        ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, due_date ASC;
        """)

    for r in rows:
        try:
            r['checklist'] = json.loads(r.get('checklist_json') or '[]')
        except Exception:
            r['checklist'] = []
    return rows

def create_task(data, user_id=None):
    now = datetime.now().isoformat()
    checklist_str = json.dumps(data.get('checklist', []))
    res = execute_mutate("""
    INSERT INTO tasks (user_id, title, category, status, progress, priority, due_date, description, checklist_json, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, [
        user_id,
        data.get('title', '新任務'),
        data.get('category', '報告'),
        data.get('status', 'pending'),
        int(data.get('progress', 0)),
        data.get('priority', 'medium'),
        data.get('due_date', ''),
        data.get('description', ''),
        checklist_str,
        now,
        now
    ])
    user_id_val = getattr(res, "last_insert_rowid", None)
    return user_id_val or 1

def update_task(task_id, data, user_id=None):
    now = datetime.now().isoformat()
    fields = []
    values = []
    for k in ['title', 'category', 'status', 'progress', 'priority', 'due_date', 'description']:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if 'checklist' in data:
        fields.append("checklist_json = ?")
        values.append(json.dumps(data['checklist']))
    fields.append("updated_at = ?")
    values.append(now)

    if user_id:
        values.append(task_id)
        values.append(user_id)
        execute_mutate(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND (user_id = ? OR user_id IS NULL);", values)
    else:
        values.append(task_id)
        execute_mutate(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?;", values)
    return True

def delete_task(task_id, user_id=None):
    if user_id:
        execute_mutate("DELETE FROM tasks WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [task_id, user_id])
    else:
        execute_mutate("DELETE FROM tasks WHERE id = ?;", [task_id])
    return True

# ----------------- User-Scoped Ideas CRUD -----------------
def get_all_ideas(user_id=None):
    if user_id:
        return execute_query("SELECT * FROM ideas WHERE user_id = ? OR user_id IS NULL ORDER BY is_starred DESC, id DESC;", [user_id])
    return execute_query("SELECT * FROM ideas ORDER BY is_starred DESC, id DESC;")

def create_idea(data, user_id=None):
    now = datetime.now().isoformat()
    res = execute_mutate("""
    INSERT INTO ideas (user_id, title, content, tags, color, is_starred, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, [
        user_id,
        data.get('title', '靈光一閃'),
        data.get('content', ''),
        data.get('tags', ''),
        data.get('color', '#fef3c7'),
        1 if data.get('is_starred') else 0,
        now,
        now
    ])
    return getattr(res, "last_insert_rowid", None) or 1

def update_idea(idea_id, data, user_id=None):
    now = datetime.now().isoformat()
    fields = []
    values = []
    for k in ['title', 'content', 'tags', 'color', 'is_starred', 'converted_to_task_id']:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    fields.append("updated_at = ?")
    values.append(now)

    if user_id:
        values.append(idea_id)
        values.append(user_id)
        execute_mutate(f"UPDATE ideas SET {', '.join(fields)} WHERE id = ? AND (user_id = ? OR user_id IS NULL);", values)
    else:
        values.append(idea_id)
        execute_mutate(f"UPDATE ideas SET {', '.join(fields)} WHERE id = ?;", values)
    return True

def delete_idea(idea_id, user_id=None):
    if user_id:
        execute_mutate("DELETE FROM ideas WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [idea_id, user_id])
    else:
        execute_mutate("DELETE FROM ideas WHERE id = ?;", [idea_id])
    return True

# ----------------- User-Scoped Business Logs CRUD -----------------
def get_all_business_logs(user_id=None):
    if user_id:
        rows = execute_query("SELECT * FROM business_logs WHERE user_id = ? OR user_id IS NULL ORDER BY id DESC;", [user_id])
    else:
        rows = execute_query("SELECT * FROM business_logs ORDER BY id DESC;")

    for r in rows:
        try:
            r['action_items'] = json.loads(r.get('action_items_json') or '[]')
        except Exception:
            r['action_items'] = []
    return rows

def create_business_log(data, user_id=None):
    now = datetime.now().isoformat()
    action_items_str = json.dumps(data.get('action_items', []))
    res = execute_mutate("""
    INSERT INTO business_logs (user_id, title, raw_transcript, summary, action_items_json, event_time, duration_minutes, calendar_status, google_calendar_url, client_name, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, [
        user_id,
        data.get('title', '業務洽談紀要'),
        data.get('raw_transcript', ''),
        data.get('summary', ''),
        action_items_str,
        data.get('event_time', ''),
        int(data.get('duration_minutes', 60)),
        data.get('calendar_status', 'unpushed'),
        data.get('google_calendar_url', ''),
        data.get('client_name', ''),
        now
    ])
    return getattr(res, "last_insert_rowid", None) or 1

def delete_business_log(log_id, user_id=None):
    if user_id:
        execute_mutate("DELETE FROM business_logs WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [log_id, user_id])
    else:
        execute_mutate("DELETE FROM business_logs WHERE id = ?;", [log_id])
    return True

# ----------------- User-Scoped Task Categories CRUD -----------------
def get_all_categories(user_id=None):
    if user_id:
        return execute_query("SELECT * FROM task_categories WHERE user_id = ? OR user_id IS NULL ORDER BY id ASC;", [user_id])
    return execute_query("SELECT * FROM task_categories ORDER BY id ASC;")

def create_category(data, user_id=None):
    now = datetime.now().isoformat()
    name = data.get('name', '').strip()
    color = data.get('color', 'indigo')
    if not name:
        raise ValueError("Category name cannot be empty")
    res = execute_mutate(
        "INSERT INTO task_categories (user_id, name, color, created_at) VALUES (?, ?, ?, ?);",
        [user_id, name, color, now]
    )
    return getattr(res, "last_insert_rowid", None) or 1

def update_category(cat_id, data, user_id=None):
    if user_id:
        rows = execute_query("SELECT name FROM task_categories WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [cat_id, user_id])
    else:
        rows = execute_query("SELECT name FROM task_categories WHERE id = ?;", [cat_id])

    old_name = rows[0]['name'] if rows else None
    name = data.get('name', '').strip()
    color = data.get('color', 'indigo')
    if not name:
        raise ValueError("Category name cannot be empty")

    if user_id:
        execute_mutate("UPDATE task_categories SET name = ?, color = ? WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [name, color, cat_id, user_id])
        if old_name and old_name != name:
            execute_mutate("UPDATE tasks SET category = ? WHERE category = ? AND (user_id = ? OR user_id IS NULL);", [name, old_name, user_id])
    else:
        execute_mutate("UPDATE task_categories SET name = ?, color = ? WHERE id = ?;", [name, color, cat_id])
        if old_name and old_name != name:
            execute_mutate("UPDATE tasks SET category = ? WHERE category = ?;", [name, old_name])
    return True

def delete_category(cat_id, user_id=None):
    if user_id:
        rows = execute_query("SELECT name FROM task_categories WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [cat_id, user_id])
        if rows:
            cat_name = rows[0]['name']
            execute_mutate("UPDATE tasks SET category = '其他' WHERE category = ? AND (user_id = ? OR user_id IS NULL);", [cat_name, user_id])
            execute_mutate("DELETE FROM task_categories WHERE id = ? AND (user_id = ? OR user_id IS NULL);", [cat_id, user_id])
    else:
        rows = execute_query("SELECT name FROM task_categories WHERE id = ?;", [cat_id])
        if rows:
            cat_name = rows[0]['name']
            execute_mutate("UPDATE tasks SET category = '其他' WHERE category = ?;", [cat_name])
            execute_mutate("DELETE FROM task_categories WHERE id = ?;", [cat_id])
    return True