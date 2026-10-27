"""
FocusFlow Database Module
SQLite-based persistent storage for Tasks, Ideas, and Business Meeting Logs.
"""
import sqlite3
import json
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(__file__), "focusflow.db")

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Table A: 靜態工作 (Static / Deliverable Tasks)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT DEFAULT '報告',  -- 報告, 簡報, 資料分析, 系統測試, 其他
        status TEXT DEFAULT 'pending', -- pending, in_progress, review, completed
        progress INTEGER DEFAULT 0,    -- 0 to 100
        priority TEXT DEFAULT 'medium', -- low, medium, high, urgent
        due_date TEXT,                 -- ISO format YYYY-MM-DD HH:MM
        description TEXT,
        checklist_json TEXT DEFAULT '[]', -- JSON array of {id, text, done}
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Table B: 創意發想 (Ideas & Sparks)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT DEFAULT '',          -- 逗號分隔標籤
        color TEXT DEFAULT '#fef3c7',  -- 便籤顏色
        is_starred INTEGER DEFAULT 0,  -- 0 or 1
        converted_to_task_id INTEGER,  -- 關聯轉化的 task id
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Table C: 業務會談與語音記錄 (Business Meetings & Voice Logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS business_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        raw_transcript TEXT NOT NULL,  -- 語音原始文字
        summary TEXT,                  -- AI 摘要重點
        action_items_json TEXT DEFAULT '[]', -- 行動清單
        event_time TEXT,               -- 解析出的關鍵時序 ISO 時間
        duration_minutes INTEGER DEFAULT 60,
        calendar_status TEXT DEFAULT 'unpushed', -- unpushed, pushed
        google_calendar_url TEXT,      -- 快速排程 URL
        client_name TEXT,              -- 客戶/對象
        created_at TEXT NOT NULL
    )
    """)

    # Table D: 靜態任務自訂類別 (Task Categories)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT 'indigo',
        created_at TEXT NOT NULL
    )
    """)

    # 預設類別初始化
    cursor.execute("SELECT COUNT(*) FROM task_categories")
    if cursor.fetchone()[0] == 0:
        default_cats = [
            ('報告', 'indigo'),
            ('簡報', 'rose'),
            ('資料分析', 'amber'),
            ('系統測試', 'emerald'),
            ('其他', 'slate')
        ]
        now = datetime.now().isoformat()
        cursor.executemany("INSERT INTO task_categories (name, color, created_at) VALUES (?, ?, ?)",
                           [(name, color, now) for name, color in default_cats])

    conn.commit()
    conn.close()

# ----------------- Tasks CRUD -----------------
def get_all_tasks():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, due_date ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for r in rows:
        try:
            r['checklist'] = json.loads(r.get('checklist_json') or '[]')
        except Exception:
            r['checklist'] = []
    return rows

def create_task(data):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    checklist_str = json.dumps(data.get('checklist', []))
    cursor.execute("""
    INSERT INTO tasks (title, category, status, progress, priority, due_date, description, checklist_json, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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
    ))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def update_task(task_id, data):
    conn = get_connection()
    cursor = conn.cursor()
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

    cursor.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True

def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return True

# ----------------- Ideas CRUD -----------------
def get_all_ideas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ideas ORDER BY is_starred DESC, id DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def create_idea(data):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO ideas (title, content, tags, color, is_starred, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('title', '靈光一閃'),
        data.get('content', ''),
        data.get('tags', ''),
        data.get('color', '#fef3c7'),
        1 if data.get('is_starred') else 0,
        now,
        now
    ))
    idea_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return idea_id

def update_idea(idea_id, data):
    conn = get_connection()
    cursor = conn.cursor()
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

    cursor.execute(f"UPDATE ideas SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True

def delete_idea(idea_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()
    conn.close()
    return True

# ----------------- Business Logs CRUD -----------------
def get_all_business_logs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM business_logs ORDER BY id DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for r in rows:
        try:
            r['action_items'] = json.loads(r.get('action_items_json') or '[]')
        except Exception:
            r['action_items'] = []
    return rows

def create_business_log(data):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    action_items_str = json.dumps(data.get('action_items', []))
    cursor.execute("""
    INSERT INTO business_logs (title, raw_transcript, summary, action_items_json, event_time, duration_minutes, calendar_status, google_calendar_url, client_name, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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
    ))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def delete_business_log(log_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM business_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    return True

# ----------------- Task Categories CRUD -----------------
def get_all_categories():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_categories ORDER BY id ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def create_category(data):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    name = data.get('name', '').strip()
    color = data.get('color', 'indigo')
    if not name:
        conn.close()
        raise ValueError("Category name cannot be empty")
    cursor.execute("INSERT INTO task_categories (name, color, created_at) VALUES (?, ?, ?)", (name, color, now))
    cat_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return cat_id

def update_category(cat_id, data):
    conn = get_connection()
    cursor = conn.cursor()
    # 獲取原舊名稱以同步更新既有任務
    cursor.execute("SELECT name FROM task_categories WHERE id = ?", (cat_id,))
    row = cursor.fetchone()
    old_name = row['name'] if row else None

    name = data.get('name', '').strip()
    color = data.get('color', 'indigo')
    if not name:
        conn.close()
        raise ValueError("Category name cannot be empty")

    cursor.execute("UPDATE task_categories SET name = ?, color = ? WHERE id = ?", (name, color, cat_id))
    if old_name and old_name != name:
        cursor.execute("UPDATE tasks SET category = ? WHERE category = ?", (name, old_name))
    conn.commit()
    conn.close()
    return True

def delete_category(cat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM task_categories WHERE id = ?", (cat_id,))
    row = cursor.fetchone()
    if row:
        cat_name = row['name']
        # 刪除類別時，將對應任務更新為 '其他'
        cursor.execute("UPDATE tasks SET category = '其他' WHERE category = ?", (cat_name,))
        cursor.execute("DELETE FROM task_categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return True

