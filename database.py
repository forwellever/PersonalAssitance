"""
FocusFlow Database Module (Turso Cloud DB / LibSQL Version)
Connects to Turso distributed LibSQL cloud database for real-time synchronization.
"""
import os
import json
import sqlite3
from datetime import datetime
import libsql_experimental as libsql

# Prefer env-provided Turso settings. If the deployment does not configure them,
# fall back to a local SQLite database instead of hanging on a remote connection.
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

    if not url or not token:
        _client = "sqlite"
        return _client

    try:
        # libsql-experimental 原生支援 libsql:// 與 https://，直接連線即可
        _client = libsql.connect(url, auth_token=token)
        return _client
    except Exception as e:
        print(f"Turso 連線失敗，錯誤訊息：{e}")
        # 若連線失敗，退回使用本地的 SQLite 檔案
        import sqlite3
        return sqlite3.connect("focusflow.db")


def execute_query(sql, params=None):
    """Executes a SELECT query and returns rows as list of dicts."""
    client = get_client()
    if client == "sqlite":
        return _sqlite_execute(sql, params)

    try:
        res = client.execute(sql, list(params) if params else [])
        cols = res.columns
        return [dict(zip(cols, row)) for row in res.rows]
    except Exception:
        global _client
        _client = "sqlite"
        return _sqlite_execute(sql, params)


def execute_mutate(sql, params=None):
    """Executes an INSERT, UPDATE, or DELETE and returns the ResultSet."""
    client = get_client()
    if client == "sqlite":
        return _sqlite_execute(sql, params)

    try:
        return client.execute(sql, list(params) if params else [])
    except Exception:
        global _client
        _client = "sqlite"
        return _sqlite_execute(sql, params)

def init_db():
    """Initializes tables in Turso Cloud DB and auto-migrates existing data if needed."""
    # 1. 建立靜態任務表
    execute_mutate("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        name TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT 'indigo',
        created_at TEXT NOT NULL
    );
    """)

    # 檢查是否需要初始化或從本機 focusflow.db 自動遷移資料
    cats = execute_query("SELECT COUNT(*) as count FROM task_categories;")
    cat_count = cats[0]['count'] if cats else 0

    if cat_count == 0:
        local_db = os.path.join(os.path.dirname(__file__), "focusflow.db")
        if os.path.exists(local_db):
            try:
                migrate_from_local_sqlite(local_db)
            except Exception as ex:
                print("⚠️ 本機資料自動遷移略過：", ex)
                seed_default_categories()
        else:
            seed_default_categories()

def seed_default_categories():
    """Inserts default categories into Turso Cloud DB."""
    default_cats = [
        ('報告', 'indigo'),
        ('簡報', 'rose'),
        ('資料分析', 'amber'),
        ('系統測試', 'emerald'),
        ('其他', 'slate')
    ]
    now = datetime.now().isoformat()
    for name, color in default_cats:
        execute_mutate(
            "INSERT INTO task_categories (name, color, created_at) VALUES (?, ?, ?);",
            [name, color, now]
        )

def migrate_from_local_sqlite(db_path):
    """Copies existing records from local SQLite focusflow.db into Turso Cloud DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. 遷移類別
    try:
        c.execute("SELECT name, color, created_at FROM task_categories;")
        rows = c.fetchall()
        for r in rows:
            execute_mutate(
                "INSERT OR IGNORE INTO task_categories (name, color, created_at) VALUES (?, ?, ?);",
                [r['name'], r['color'], r['created_at']]
            )
    except Exception:
        seed_default_categories()

    # 2. 遷移任務
    try:
        c.execute("SELECT title, category, status, progress, priority, due_date, description, checklist_json, created_at, updated_at FROM tasks;")
        for r in c.fetchall():
            execute_mutate(
                """INSERT INTO tasks (title, category, status, progress, priority, due_date, description, checklist_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                [r['title'], r['category'], r['status'], r['progress'], r['priority'], r['due_date'], r['description'], r['checklist_json'], r['created_at'], r['updated_at']]
            )
    except Exception:
        pass

    # 3. 遷移靈感
    try:
        c.execute("SELECT title, content, tags, color, is_starred, converted_to_task_id, created_at, updated_at FROM ideas;")
        for r in c.fetchall():
            execute_mutate(
                """INSERT INTO ideas (title, content, tags, color, is_starred, converted_to_task_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                [r['title'], r['content'], r['tags'], r['color'], r['is_starred'], r['converted_to_task_id'], r['created_at'], r['updated_at']]
            )
    except Exception:
        pass

    # 4. 遷移業務會談紀錄
    try:
        c.execute("SELECT title, raw_transcript, summary, action_items_json, event_time, duration_minutes, calendar_status, google_calendar_url, client_name, created_at FROM business_logs;")
        for r in c.fetchall():
            execute_mutate(
                """INSERT INTO business_logs (title, raw_transcript, summary, action_items_json, event_time, duration_minutes, calendar_status, google_calendar_url, client_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                [r['title'], r['raw_transcript'], r['summary'], r['action_items_json'], r['event_time'], r['duration_minutes'], r['calendar_status'], r['google_calendar_url'], r['client_name'], r['created_at']]
            )
    except Exception:
        pass

    conn.close()
    print("✅ 已成功將本機 SQLite 既有資料同步遷移至 Turso Cloud DB！")

# ----------------- Tasks CRUD -----------------
def get_all_tasks():
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

def create_task(data):
    now = datetime.now().isoformat()
    checklist_str = json.dumps(data.get('checklist', []))
    res = execute_mutate("""
    INSERT INTO tasks (title, category, status, progress, priority, due_date, description, checklist_json, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, [
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
    return res.last_insert_rowid

def update_task(task_id, data):
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
    values.append(task_id)

    execute_mutate(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?;", values)
    return True

def delete_task(task_id):
    execute_mutate("DELETE FROM tasks WHERE id = ?;", [task_id])
    return True

# ----------------- Ideas CRUD -----------------
def get_all_ideas():
    return execute_query("SELECT * FROM ideas ORDER BY is_starred DESC, id DESC;")

def create_idea(data):
    now = datetime.now().isoformat()
    res = execute_mutate("""
    INSERT INTO ideas (title, content, tags, color, is_starred, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, [
        data.get('title', '靈光一閃'),
        data.get('content', ''),
        data.get('tags', ''),
        data.get('color', '#fef3c7'),
        1 if data.get('is_starred') else 0,
        now,
        now
    ])
    return res.last_insert_rowid

def update_idea(idea_id, data):
    now = datetime.now().isoformat()
    fields = []
    values = []
    for k in ['title', 'content', 'tags', 'color', 'is_starred', 'converted_to_task_id']:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    fields.append("updated_at = ?")
    values.append(now)
    values.append(idea_id)

    execute_mutate(f"UPDATE ideas SET {', '.join(fields)} WHERE id = ?;", values)
    return True

def delete_idea(idea_id):
    execute_mutate("DELETE FROM ideas WHERE id = ?;", [idea_id])
    return True

# ----------------- Business Logs CRUD -----------------
def get_all_business_logs():
    rows = execute_query("SELECT * FROM business_logs ORDER BY id DESC;")
    for r in rows:
        try:
            r['action_items'] = json.loads(r.get('action_items_json') or '[]')
        except Exception:
            r['action_items'] = []
    return rows

def create_business_log(data):
    now = datetime.now().isoformat()
    action_items_str = json.dumps(data.get('action_items', []))
    res = execute_mutate("""
    INSERT INTO business_logs (title, raw_transcript, summary, action_items_json, event_time, duration_minutes, calendar_status, google_calendar_url, client_name, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, [
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
    return res.last_insert_rowid

def delete_business_log(log_id):
    execute_mutate("DELETE FROM business_logs WHERE id = ?;", [log_id])
    return True

# ----------------- Task Categories CRUD -----------------
def get_all_categories():
    return execute_query("SELECT * FROM task_categories ORDER BY id ASC;")

def create_category(data):
    now = datetime.now().isoformat()
    name = data.get('name', '').strip()
    color = data.get('color', 'indigo')
    if not name:
        raise ValueError("Category name cannot be empty")
    res = execute_mutate("INSERT INTO task_categories (name, color, created_at) VALUES (?, ?, ?);", [name, color, now])
    return res.last_insert_rowid

def update_category(cat_id, data):
    rows = execute_query("SELECT name FROM task_categories WHERE id = ?;", [cat_id])
    old_name = rows[0]['name'] if rows else None

    name = data.get('name', '').strip()
    color = data.get('color', 'indigo')
    if not name:
        raise ValueError("Category name cannot be empty")

    execute_mutate("UPDATE task_categories SET name = ?, color = ? WHERE id = ?;", [name, color, cat_id])
    if old_name and old_name != name:
        execute_mutate("UPDATE tasks SET category = ? WHERE category = ?;", [name, old_name])
    return True

def delete_category(cat_id):
    rows = execute_query("SELECT name FROM task_categories WHERE id = ?;", [cat_id])
    if rows:
        cat_name = rows[0]['name']
        execute_mutate("UPDATE tasks SET category = '其他' WHERE category = ?;", [cat_name])
        execute_mutate("DELETE FROM task_categories WHERE id = ?;", [cat_id])
    return True
