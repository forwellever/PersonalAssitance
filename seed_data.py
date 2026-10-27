"""
Seed demonstration data for FocusFlow
"""
import database
import ai_engine
import calendar_service
from datetime import datetime, timedelta

def seed():
    database.init_db()

    # 1. 靜態工作 (A)
    tasks = [
        {
            "title": "Q4 營運分析報告撰寫",
            "category": "報告",
            "status": "in_progress",
            "progress": 60,
            "priority": "high",
            "due_date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT17:00"),
            "description": "彙整業務各產品線營收與轉換率，完成 PDF 與主管簽核版。",
            "checklist": [
                {"text": "收集數據資料", "done": True},
                {"text": "繪製視覺化圖表", "done": True},
                {"text": "撰寫洞察結論", "done": False}
            ]
        },
        {
            "title": "新版客戶提案簡報設計",
            "category": "簡報",
            "status": "pending",
            "progress": 10,
            "priority": "urgent",
            "due_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT14:00"),
            "description": "製作針對大型企業客戶的解決方案簡報（15頁）。",
            "checklist": []
        },
        {
            "title": "行銷漏斗轉換率深入資料分析",
            "category": "資料分析",
            "status": "review",
            "progress": 90,
            "priority": "medium",
            "due_date": (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%dT18:00"),
            "description": "分析註冊至付費的各階段流失點與廣告投放效益比。",
            "checklist": []
        },
        {
            "title": "API 效能壓力與安全性測試",
            "category": "系統測試",
            "status": "completed",
            "progress": 100,
            "priority": "high",
            "due_date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT12:00"),
            "description": "驗證在高併發情況下後端延遲率低於 200ms。",
            "checklist": []
        }
    ]

    for t in tasks:
        database.create_task(t)

    # 2. 創意發想 (B)
    ideas = [
        {
            "title": "語音自動生成每日 Standup 筆記",
            "content": "早上上班只要用手機說一段 30 秒短話，AI 自動整理成昨天的完成進度與今日計畫。",
            "tags": "語音,效率,AI",
            "color": "#fef3c7",
            "is_starred": 1
        },
        {
            "title": "為重要客戶客製化互動儀表板",
            "content": "在業務洽談時，可以直接展示帶有客戶品牌 Logo 的即時 demo 介面，提高簽約意願。",
            "tags": "業務,客戶體驗",
            "color": "#dbeafe",
            "is_starred": 0
        },
        {
            "title": "週五自動提醒回顧未完成之靜態工作",
            "content": "結合 Google Calendar 與通知，每週五下午 4:30 自動盤點並建議調整排程。",
            "tags": "排程,提醒",
            "color": "#dcfce7",
            "is_starred": 1
        }
    ]

    for i in ideas:
        database.create_idea(i)

    # 3. 業務會談與行事曆 (C)
    sample_text = "今天下午與宏達科技張經理電話討論，確認需要在下週三下午兩點前交付測試報告與系統驗收規格，另外需要安排週五下午三點的線上校對會議。"
    analysis = ai_engine.parse_meeting_transcript(sample_text)
    
    # 計算 Google Calendar URL
    event_dt = datetime.strptime(analysis['event_time'], "%Y-%m-%d %H:%M") if analysis.get('event_time') else (datetime.now() + timedelta(days=3))
    analysis['google_calendar_url'] = calendar_service.generate_google_calendar_url(
        title=analysis['title'],
        start_dt=event_dt,
        duration_minutes=60,
        description=analysis['summary']
    )
    analysis['raw_transcript'] = sample_text
    database.create_business_log(analysis)

    print("✅ Seed data successfully generated!")

if __name__ == "__main__":
    seed()
