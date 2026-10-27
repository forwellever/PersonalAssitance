"""
FocusFlow AI Engine
Speech transcript analysis, action item extraction, and temporal parsing for calendar scheduling.
"""
import re
from datetime import datetime, timedelta

def parse_meeting_transcript(raw_text: str):
    """
    Analyzes raw meeting transcript to extract:
    - title
    - client_name
    - summary
    - action_items
    - event_time (ISO string)
    """
    text = raw_text.strip()
    if not text:
        return {
            "title": "空白會談紀錄",
            "client_name": "",
            "summary": "無內容",
            "action_items": [],
            "event_time": ""
        }

    # 1. 提煉標題與對象
    client_name = ""
    client_match = re.search(r'(與|和|跟)?([\u4e00-\u9fa5A-Za-z0-9]+(公司|團隊|客戶|經理|先生|小姐|總監|處長|副總|董事長))', text)
    if client_match:
        client_name = client_match.group(2)

    # 2. 關鍵時序解析 (Temporal Entity Parsing)
    parsed_dt = extract_datetime_from_text(text)
    event_time_str = parsed_dt.strftime("%Y-%m-%d %H:%M") if parsed_dt else ""

    # 3. 提煉 Action Items (行動清單)
    action_items = []
    # 尋找待辦詞彙模式
    action_patterns = [
        r'(?:需要|記得|要|必須|務必|代辦|請)([^，。！？\n]{4,35})',
        r'(?:預計|準備|安排|確認|交付|完成)([^，。！？\n]{4,35})',
        r'([A-Za-z0-9\u4e00-\u9fa5]+在[^，。！？\n]{2,10}(?:前|時)(?:完成|送出|交付|開會|確認)[^，。！？\n]{0,20})'
    ]
    seen_items = set()
    for pat in action_patterns:
        for m in re.finditer(pat, text):
            item = m.group(0).strip("，。！？ ")
            if len(item) >= 4 and item not in seen_items:
                seen_items.add(item)
                action_items.append({"text": item, "done": False})

    # 如果沒有特定觸發詞，但有條列或逗號，切片提煉
    if not action_items:
        sentences = [s.strip() for s in re.split(r'[。！？\n]', text) if len(s.strip()) > 5]
        for s in sentences[:3]:
            action_items.append({"text": s, "done": False})

    # 4. 產生摘要 (Summary)
    summary_lines = []
    if client_name:
        summary_lines.append(f"• 會談對象：{client_name}")
    if event_time_str:
        summary_lines.append(f"• 約定時序：{event_time_str}")
    
    # 抽取核心句子
    core_sentences = [s.strip() for s in re.split(r'[。！？\n]', text) if len(s.strip()) > 6]
    for s in core_sentences[:3]:
        summary_lines.append(f"• {s}")
    
    summary = "\n".join(summary_lines) if summary_lines else text[:100]

    # 5. 標題生成
    title = f"業務會談：{client_name}" if client_name else "業務會談備忘"
    if len(core_sentences) > 0 and len(core_sentences[0]) < 20:
        title = f"{title} - {core_sentences[0]}"

    return {
        "title": title[:30],
        "client_name": client_name,
        "summary": summary,
        "action_items": action_items[:5],
        "event_time": event_time_str
    }

def extract_datetime_from_text(text: str):
    """
    Parses relative/absolute temporal references from Chinese speech text:
    - 今天 / 明天 / 後天
    - 下週[一至日] / 這週[一至日] / 禮拜[一至日]
    - 上午 / 下午 / 早上 / 晚上 / [0-24]點 / [0-59]分
    - X月X號 / X月X日
    """
    now = datetime.now()
    target_date = now.date()
    target_hour = 10  # 預設上午 10:00
    target_minute = 0
    found_time = False

    # 1. 辨識日期偏移
    if "大後天" in text:
        target_date = (now + timedelta(days=3)).date()
        found_time = True
    elif "後天" in text:
        target_date = (now + timedelta(days=2)).date()
        found_time = True
    elif "明天" in text:
        target_date = (now + timedelta(days=1)).date()
        found_time = True
    elif "今天" in text:
        target_date = now.date()
        found_time = True

    # 辨識星期 (例如：下週三、這週五、禮拜二)
    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
                   "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}
    week_match = re.search(r'(下下週|下週|這週|本週|禮拜|星期)([一二三四五六日天1234567])', text)
    if week_match:
        prefix = week_match.group(1)
        w_char = week_match.group(2)
        target_w = weekday_map.get(w_char, 0)
        current_w = now.weekday()
        days_ahead = target_w - current_w
        if "下下週" in prefix:
            days_ahead += 14
        elif "下週" in prefix:
            days_ahead += 7
        elif days_ahead <= 0:
            days_ahead += 7
        target_date = (now + timedelta(days=days_ahead)).date()
        found_time = True

    # 辨識幾月幾號 (例如：11月15日, 11/15, 12月3號)
    date_match = re.search(r'(\d{1,2})[月/](\d{1,2})[號日]?', text)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = now.year
        if month < now.month or (month == now.month and day < now.day):
            year += 1
        try:
            target_date = datetime(year, month, day).date()
            found_time = True
        except ValueError:
            pass

    # 2. 辨識時間 (上午/下午/晚上/點/分，支援阿拉伯數字與中文數字)
    # 將中文數字轉為阿拉伯數字
    cn_num_map = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
    normalized_text = text
    for cn, num in cn_num_map.items():
        normalized_text = re.sub(rf'{cn}([點:時])', rf'{num}\1', normalized_text)
    
    hour_match = re.search(r'(上午|下午|早上|中午|晚上)?\s*(\d{1,2})[點:時](\s*(\d{1,2})分?)?', normalized_text)
    if hour_match:
        period = hour_match.group(1) or ""
        hour = int(hour_match.group(2))
        minute = int(hour_match.group(4)) if hour_match.group(4) else 0

        if period in ["下午", "晚上"] and hour < 12:
            hour += 12
        elif period in ["中午"] and hour < 11:
            hour += 12

        target_hour = hour
        target_minute = minute
        found_time = True
    elif "下午" in text or "晚上" in text:
        target_hour = 14
        found_time = True
    elif "上午" in text or "早上" in text:
        target_hour = 10
        found_time = True

    if found_time:
        return datetime(target_date.year, target_date.month, target_date.day, target_hour, target_minute)
    return None
