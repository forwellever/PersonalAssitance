"""
FocusFlow Backend Integration Tests
"""
import unittest
import json
from datetime import datetime
import ai_engine
import calendar_service
import database

class TestFocusFlow(unittest.TestCase):
    def setUp(self):
        database.init_db()

    def test_task_crud(self):
        task_id = database.create_task({
            "title": "測試報告專案",
            "category": "報告",
            "status": "pending",
            "progress": 25,
            "priority": "high",
            "due_date": "2026-10-30 18:00",
            "description": "測試說明",
            "checklist": [{"text": "第1項", "done": False}]
        })
        self.assertIsNotNone(task_id)

        tasks = database.get_all_tasks()
        found = next((t for t in tasks if t['id'] == task_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found['title'], "測試報告專案")
        self.assertEqual(found['progress'], 25)

        # Update
        database.update_task(task_id, {"progress": 100, "status": "completed"})
        tasks_updated = database.get_all_tasks()
        found_updated = next((t for t in tasks_updated if t['id'] == task_id), None)
        self.assertEqual(found_updated['progress'], 100)
        self.assertEqual(found_updated['status'], "completed")

        # Cleanup
        database.delete_task(task_id)

    def test_ai_temporal_and_summary(self):
        text = "跟台灣大車隊李處長約定，必須在明天下午三點提供系統測試報告與簡報架構。"
        parsed = ai_engine.parse_meeting_transcript(text)
        self.assertIn("處長", parsed['client_name'])
        self.assertTrue(len(parsed['action_items']) > 0)
        self.assertIsNotNone(parsed['event_time'])
        dt = datetime.strptime(parsed['event_time'], "%Y-%m-%d %H:%M")
        self.assertEqual(dt.hour, 15)

        # Test another variation: 下週三早上十點
        text2 = "與宏達科技張經理確認，下週三早上10點前交付資料分析成果"
        parsed2 = ai_engine.parse_meeting_transcript(text2)
        self.assertIsNotNone(parsed2['event_time'])
        dt2 = datetime.strptime(parsed2['event_time'], "%Y-%m-%d %H:%M")
        self.assertEqual(dt2.hour, 10)
        self.assertEqual(dt2.weekday(), 2)  # Wednesday

    def test_calendar_service(self):
        dt = datetime(2026, 11, 5, 14, 30)
        url = calendar_service.generate_google_calendar_url(
            title="測試會議",
            start_dt=dt,
            duration_minutes=60,
            description="測試備忘"
        )
        self.assertIn("https://calendar.google.com/calendar/render", url)
        self.assertIn("20261105T143000", url)

        ics = calendar_service.generate_ics_content("測試會議", dt)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("SUMMARY:測試會議", ics)

    def test_category_crud(self):
        # 1. 建立類別
        cat_id = database.create_category({"name": "自動化部署", "color": "cyan"})
        self.assertIsNotNone(cat_id)

        # 2. 讀取驗證
        cats = database.get_all_categories()
        found = next((c for c in cats if c['id'] == cat_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found['name'], "自動化部署")

        # 3. 修改類別
        database.update_category(cat_id, {"name": "DevOps維運", "color": "purple"})
        cats_after = database.get_all_categories()
        found_updated = next((c for c in cats_after if c['id'] == cat_id), None)
        self.assertEqual(found_updated['name'], "DevOps維運")
        self.assertEqual(found_updated['color'], "purple")

        # 4. 刪除類別
        database.delete_category(cat_id)
        cats_final = database.get_all_categories()
        self.assertIsNone(next((c for c in cats_final if c['id'] == cat_id), None))

    def test_idea_star_and_supplement(self):
        # 1. 建立靈感
        idea_id = database.create_idea({
            "title": "AI 智慧回覆機制",
            "content": "初步想法：分析顧客來信並草擬回覆。",
            "tags": "AI,客服",
            "is_starred": 0
        })

        # 2. 標記星號與追加內容
        supplement = "\n\n[2026-10-27 補充]：整合 Gmail 擴充套件。"
        database.update_idea(idea_id, {
            "content": "初步想法：分析顧客來信並草擬回覆。" + supplement,
            "is_starred": 1
        })

        ideas = database.get_all_ideas()
        target = next((i for i in ideas if i['id'] == idea_id), None)
        self.assertIsNotNone(target)
        self.assertEqual(target['is_starred'], 1)
        self.assertIn("Gmail 擴充套件", target['content'])

        # 清理
        database.delete_idea(idea_id)

    def test_user_auth_flow(self):
        email = "alice_test@example.com"
        # 1. 發送驗證碼
        otp_res = database.generate_and_save_otp(email)
        self.assertTrue(otp_res['success'])

        # 2. 獲取驗證碼
        otps = database.execute_query("SELECT code FROM email_otps WHERE email = ? AND used = 0 ORDER BY id DESC LIMIT 1;", [email])
        self.assertTrue(len(otps) > 0)
        code = otps[0]['code']

        # 3. 驗證登入
        login_res = database.verify_otp_and_login(email, code)
        self.assertTrue(login_res['success'])
        self.assertIsNotNone(login_res.get('token'))
        token = login_res['token']

        # 4. 透過 Token 取得使用者資訊
        user = database.get_user_by_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user['email'], email)

        # 5. 重複使用同一驗證碼應失敗
        second_login = database.verify_otp_and_login(email, code)
        self.assertFalse(second_login['success'])

        # 6. 登出
        database.delete_session(token)
        user_after_logout = database.get_user_by_token(token)
        self.assertIsNone(user_after_logout)

    def test_multi_user_isolation(self):
        u1 = database.get_or_create_user("user_a@example.com")
        u2 = database.get_or_create_user("user_b@example.com")

        t1_id = database.create_task({"title": "User A 報告", "category": "報告"}, user_id=u1['id'])
        t2_id = database.create_task({"title": "User B 簡報", "category": "簡報"}, user_id=u2['id'])

        u1_tasks = database.get_all_tasks(user_id=u1['id'])
        u2_tasks = database.get_all_tasks(user_id=u2['id'])

        u1_titles = [t['title'] for t in u1_tasks]
        u2_titles = [t['title'] for t in u2_tasks]

        self.assertIn("User A 報告", u1_titles)
        self.assertNotIn("User B 簡報", u1_titles)

        self.assertIn("User B 簡報", u2_titles)
        self.assertNotIn("User A 報告", u2_titles)

        # 清理
        database.delete_task(t1_id, user_id=u1['id'])
        database.delete_task(t2_id, user_id=u2['id'])

if __name__ == '__main__':
    unittest.main()
