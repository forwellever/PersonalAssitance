"""
FocusFlow Calendar Service
Integrates with Google Calendar via URL action protocol and provides standard iCalendar (.ics) exports.
"""
import urllib.parse
from datetime import datetime, timedelta

def format_gcal_date(dt: datetime) -> str:
    """Format datetime into Google Calendar standard timestamp: YYYYMMDDTHHMMSS"""
    return dt.strftime("%Y%m%dT%H%M%S")

def generate_google_calendar_url(title: str, start_dt: datetime, duration_minutes: int = 60, description: str = "", location: str = "") -> str:
    """
    Generates a zero-friction, direct Google Calendar event creation link.
    User can click this link on desktop or mobile to prefill and add the event with reminders.
    """
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    
    dates_param = f"{format_gcal_date(start_dt)}/{format_gcal_date(end_dt)}"
    
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": description,
        "location": location
    }
    
    query_string = urllib.parse.urlencode(params)
    return f"https://calendar.google.com/calendar/render?{query_string}"

def generate_ics_content(title: str, start_dt: datetime, duration_minutes: int = 60, description: str = "", location: str = "") -> str:
    """Generates standard iCalendar (.ics) payload compatible with Google, Apple, and Outlook calendars."""
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_dt.strftime("%Y%m%dT%H%M%S")
    dtend = end_dt.strftime("%Y%m%dT%H%M%S")
    
    safe_desc = description.replace("\n", "\\n").replace(",", "\\,")
    
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FocusFlow//Smart Task & Calendar//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"DTSTAMP:{dtstamp}",
        f"UID:{dtstamp}-{int(start_dt.timestamp())}@focusflow.local",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{title}",
        f"DESCRIPTION:{safe_desc}",
        f"LOCATION:{location}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:提醒通知",
        "TRIGGER:-PT15M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    return "\r\n".join(ics_lines)
