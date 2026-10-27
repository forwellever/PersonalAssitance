"""
FocusFlow Backend Application Server
High performance, zero-dependency REST API and static web server built on Python standard libraries.
"""
import http.server
import socketserver
import json
import os
import re
import urllib.parse
from datetime import datetime

import database
import ai_engine
import calendar_service

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

class FocusFlowHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def _read_body_json(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0:
                return {}
            raw_data = self.rfile.read(content_length).decode('utf-8')
            return json.loads(raw_data)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API Routes
        if path == '/api/tasks':
            tasks = database.get_all_tasks()
            return self._send_json({"success": True, "data": tasks})

        elif path == '/api/ideas':
            ideas = database.get_all_ideas()
            return self._send_json({"success": True, "data": ideas})

        elif path == '/api/categories':
            categories = database.get_all_categories()
            return self._send_json({"success": True, "data": categories})

        elif path == '/api/business':
            logs = database.get_all_business_logs()
            return self._send_json({"success": True, "data": logs})

        elif path.startswith('/api/business/') and path.endswith('/ics'):
            # Download ICS
            match = re.match(r'^/api/business/(\d+)/ics$', path)
            if match:
                log_id = int(match.group(1))
                logs = database.get_all_business_logs()
                target_log = next((l for l in logs if l['id'] == log_id), None)
                if target_log and target_log.get('event_time'):
                    try:
                        dt = datetime.fromisoformat(target_log['event_time'])
                    except Exception:
                        dt = datetime.now()
                    ics_data = calendar_service.generate_ics_content(
                        title=target_log['title'],
                        start_dt=dt,
                        duration_minutes=target_log.get('duration_minutes', 60),
                        description=target_log.get('summary', '')
                    ).encode('utf-8')

                    self.send_response(200)
                    self.send_header('Content-Type', 'text/calendar; charset=utf-8')
                    self.send_header('Content-Disposition', f'attachment; filename="event_{log_id}.ics"')
                    self.send_header('Content-Length', str(len(ics_data)))
                    self.end_headers()
                    self.wfile.write(ics_data)
                    return
                return self._send_json({"error": "Event time not specified"}, status_code=400)

        elif path == '/api/stats':
            tasks = database.get_all_tasks()
            ideas = database.get_all_ideas()
            logs = database.get_all_business_logs()

            pending_tasks = sum(1 for t in tasks if t['status'] != 'completed')
            completed_tasks = sum(1 for t in tasks if t['status'] == 'completed')
            total_ideas = len(ideas)
            starred_ideas = sum(1 for i in ideas if i['is_starred'])
            total_meetings = len(logs)
            scheduled_meetings = sum(1 for l in logs if l.get('event_time'))

            return self._send_json({
                "success": True,
                "data": {
                    "pending_tasks": pending_tasks,
                    "completed_tasks": completed_tasks,
                    "total_ideas": total_ideas,
                    "starred_ideas": starred_ideas,
                    "total_meetings": total_meetings,
                    "scheduled_meetings": scheduled_meetings
                }
            })

        # Static file fallback (index.html for root)
        if path == '/' or path == '':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body_json()

        # 1. 任務新增
        if path == '/api/tasks':
            task_id = database.create_task(body)
            return self._send_json({"success": True, "id": task_id}, status_code=201)

        # 2. 靈感新增
        elif path == '/api/ideas':
            idea_id = database.create_idea(body)
            return self._send_json({"success": True, "id": idea_id}, status_code=201)

        # 2.5 類別新增
        elif path == '/api/categories':
            try:
                cat_id = database.create_category(body)
                return self._send_json({"success": True, "id": cat_id}, status_code=201)
            except Exception as e:
                return self._send_json({"error": str(e)}, status_code=400)

        # 3. 靈感轉換為任務 (Idea -> Task conversion)
        elif re.match(r'^/api/ideas/(\d+)/convert$', path):
            match = re.match(r'^/api/ideas/(\d+)/convert$', path)
            idea_id = int(match.group(1))
            ideas = database.get_all_ideas()
            target_idea = next((i for i in ideas if i['id'] == idea_id), None)
            if not target_idea:
                return self._send_json({"error": "Idea not found"}, status_code=404)

            # Create task from idea
            task_data = {
                "title": target_idea['title'],
                "category": body.get("category", "資料分析"),
                "status": "pending",
                "progress": 0,
                "priority": body.get("priority", "medium"),
                "due_date": body.get("due_date", ""),
                "description": target_idea.get('content', ''),
                "checklist": [{"text": "啟動專案構思", "done": False}]
            }
            task_id = database.create_task(task_data)
            database.update_idea(idea_id, {"converted_to_task_id": task_id})
            return self._send_json({"success": True, "task_id": task_id})

        # 4. 業務語音與文字分析
        elif path == '/api/business/analyze':
            raw_text = body.get('text', '')
            analysis = ai_engine.parse_meeting_transcript(raw_text)

            # Generate Google Calendar URL if event time was detected
            gcal_url = ""
            if analysis.get('event_time'):
                try:
                    dt = datetime.strptime(analysis['event_time'], "%Y-%m-%d %H:%M")
                    gcal_url = calendar_service.generate_google_calendar_url(
                        title=analysis['title'],
                        start_dt=dt,
                        duration_minutes=60,
                        description=analysis['summary']
                    )
                except Exception as e:
                    print("Date parsing error:", e)

            analysis['google_calendar_url'] = gcal_url
            return self._send_json({"success": True, "data": analysis})

        # 5. 儲存業務會談紀要
        elif path == '/api/business':
            # Auto-calculate gcal_url if missing and event_time exists
            if not body.get('google_calendar_url') and body.get('event_time'):
                try:
                    dt = datetime.strptime(body['event_time'], "%Y-%m-%d %H:%M")
                    body['google_calendar_url'] = calendar_service.generate_google_calendar_url(
                        title=body.get('title', '業務洽談'),
                        start_dt=dt,
                        duration_minutes=int(body.get('duration_minutes', 60)),
                        description=body.get('summary', '')
                    )
                except Exception:
                    pass

            log_id = database.create_business_log(body)
            return self._send_json({"success": True, "id": log_id}, status_code=201)

        return self._send_json({"error": "Endpoint not found"}, status_code=404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body_json()

        # Update Task
        match_task = re.match(r'^/api/tasks/(\d+)$', path)
        if match_task:
            task_id = int(match_task.group(1))
            database.update_task(task_id, body)
            return self._send_json({"success": True})

        # Update Idea
        match_idea = re.match(r'^/api/ideas/(\d+)$', path)
        if match_idea:
            idea_id = int(match_idea.group(1))
            database.update_idea(idea_id, body)
            return self._send_json({"success": True})

        # Update Category
        match_cat = re.match(r'^/api/categories/(\d+)$', path)
        if match_cat:
            cat_id = int(match_cat.group(1))
            try:
                database.update_category(cat_id, body)
                return self._send_json({"success": True})
            except Exception as e:
                return self._send_json({"error": str(e)}, status_code=400)

        return self._send_json({"error": "Endpoint not found"}, status_code=404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Delete Task
        match_task = re.match(r'^/api/tasks/(\d+)$', path)
        if match_task:
            task_id = int(match_task.group(1))
            database.delete_task(task_id)
            return self._send_json({"success": True})

        # Delete Idea
        match_idea = re.match(r'^/api/ideas/(\d+)$', path)
        if match_idea:
            idea_id = int(match_idea.group(1))
            database.delete_idea(idea_id)
            return self._send_json({"success": True})

        # Delete Category
        match_cat = re.match(r'^/api/categories/(\d+)$', path)
        if match_cat:
            cat_id = int(match_cat.group(1))
            database.delete_category(cat_id)
            return self._send_json({"success": True})

        # Delete Business Log
        match_business = re.match(r'^/api/business/(\d+)$', path)
        if match_business:
            log_id = int(match_business.group(1))
            database.delete_business_log(log_id)
            return self._send_json({"success": True})

        return self._send_json({"error": "Endpoint not found"}, status_code=404)

def run_server(port=PORT):
    database.init_db()
    with socketserver.TCPServer(("", port), FocusFlowHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"🚀 FocusFlow Server running at http://localhost:{port}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()
