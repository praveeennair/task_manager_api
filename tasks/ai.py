import re
import datetime
from typing import Optional, Dict, Any, List
from django.conf import settings
from .errors import error_response


def parse_task_text(text: str, today: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Parses natural language task text into structured task dictionary.
    
    Signature:
        parse_task_text(text: str, today: Optional[datetime.date] = None) -> dict[str, Any]
        
    Returns:
        {
            "title": str,
            "description": str,
            "due_date": str (YYYY-MM-DD) or None,
            "recurrence": str or None,
            "priority": str
        }
    """
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Input text must be a non-empty string")

    raw_text = text.strip()
    clean_text = raw_text

    if today is None:
        today = datetime.date.today()

    due_date = None
    recurrence = None
    priority = "medium"

    # Priority extraction
    if re.search(r'\b(urgent|critical|asap|high priority)\b', clean_text, re.IGNORECASE):
        priority = "high"
    elif re.search(r'\b(low priority|whenever|when free|low)\b', clean_text, re.IGNORECASE):
        priority = "low"

    # Recurrence detection (order specific phrases before general ones)
    rec_patterns = [
        (r'\b(on the (\d+)(?:st|nd|rd|th)? of every month)\b', None),
        (r'\b(every\s+month|monthly)\b', 'monthly'),
        (r'\b(every\s+week|weekly)\b', 'weekly'),
        (r'\b(every\s+day|daily)\b', 'daily'),
        (r'\b(every\s+year|annually|yearly)\b', 'annually'),
        (r'\b(every\s+\w+day)\b', None),
    ]

    for pat, label in rec_patterns:
        match = re.search(pat, clean_text, re.IGNORECASE)
        if match:
            recurrence = label if label else match.group(0).lower()
            # If pattern matched "on the X of every month", extract target day
            if match.lastindex and match.lastindex >= 2 and match.group(2):
                target_day = int(match.group(2))
                if target_day >= today.day:
                    due_date = datetime.date(today.year, today.month, target_day)
                else:
                    next_month = today.month + 1 if today.month < 12 else 1
                    next_year = today.year if today.month < 12 else today.year + 1
                    due_date = datetime.date(next_year, next_month, target_day)
            clean_text = re.sub(pat, '', clean_text, flags=re.IGNORECASE).strip()
            break

    # Date extraction
    # 1. "tomorrow"
    if re.search(r'\btomorrow\b', clean_text, re.IGNORECASE):
        due_date = today + datetime.timedelta(days=1)
        clean_text = re.sub(r'\btomorrow\b', '', clean_text, flags=re.IGNORECASE).strip()

    # 2. "today"
    elif re.search(r'\btoday\b', clean_text, re.IGNORECASE):
        due_date = today
        clean_text = re.sub(r'\btoday\b', '', clean_text, flags=re.IGNORECASE).strip()

    # 3. Explicit YYYY-MM-DD
    elif date_match := re.search(r'\b(\d{4}-\d{2}-\d{2})\b', clean_text):
        try:
            due_date = datetime.date.fromisoformat(date_match.group(1))
            clean_text = clean_text.replace(date_match.group(1), '').strip()
        except ValueError:
            pass

    # 4. "in X days"
    elif in_days_match := re.search(r'\bin\s+(\d+)\s+days?\b', clean_text, re.IGNORECASE):
        days = int(in_days_match.group(1))
        due_date = today + datetime.timedelta(days=days)
        clean_text = re.sub(r'\bin\s+\d+\s+days?\b', '', clean_text, flags=re.IGNORECASE).strip()

    # 5. "on the 1st", "on the 15th", etc.
    elif day_match := re.search(r'\bon the (\d+)(?:st|nd|rd|th)?\b', clean_text, re.IGNORECASE):
        target_day = int(day_match.group(1))
        try:
            if target_day >= today.day:
                due_date = datetime.date(today.year, today.month, target_day)
            else:
                next_month = today.month + 1 if today.month < 12 else 1
                next_year = today.year if today.month < 12 else today.year + 1
                due_date = datetime.date(next_year, next_month, target_day)
        except ValueError:
            pass
        clean_text = re.sub(r'\bon the \d+(?:st|nd|rd|th)?\b', '', clean_text, flags=re.IGNORECASE).strip()

    # If recurrence is monthly on the 1st, set default due_date to upcoming 1st
    if recurrence and '1st' in recurrence and not due_date:
        if today.day == 1:
            due_date = today
        else:
            next_month = today.month + 1 if today.month < 12 else 1
            next_year = today.year if today.month < 12 else today.year + 1
            due_date = datetime.date(next_year, next_month, 1)

    # Clean prefixes like "Remind me to ", "Remember to ", "Please "
    clean_title = re.sub(r'^(remind me to|remember to|please|i need to|task:?)\s+', '', clean_text, flags=re.IGNORECASE).strip()
    while re.search(r'\s+(on|at|by|due|for|of)$', clean_title, flags=re.IGNORECASE):
        clean_title = re.sub(r'\s+(on|at|by|due|for|of)$', '', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    if not clean_title:
        clean_title = raw_text

    # Capitalize first character
    clean_title = clean_title[0].upper() + clean_title[1:] if clean_title else "New Task"

    return {
        "title": clean_title,
        "description": raw_text,
        "due_date": due_date.isoformat() if due_date else None,
        "recurrence": recurrence,
        "priority": priority,
    }


def break_down_task(task) -> List[Dict[str, Any]]:
    """
    Breaks down a parent task into subtask dictionaries using rule-based parsing.
    Splits by clauses ('and', commas, semicolons, steps) or creates structured phases.
    """
    description = task.description or task.title
    title = task.title

    # Check for bullet points or numbered lists
    lines = [line.strip() for line in description.splitlines() if line.strip()]
    subtask_candidates = []

    for line in lines:
        cleaned = re.sub(r'^(\d+[\.\)]|\-|\*)\s*', '', line).strip()
        if cleaned and cleaned.lower() != title.lower():
            subtask_candidates.append(cleaned)

    # Check for "and", commas, or semicolons if no bullet lines found
    if len(subtask_candidates) <= 1:
        text_to_split = re.sub(r'^(please|remind me to|i need to)\s+', '', title, flags=re.IGNORECASE)
        # Split on commas, semicolons, or " and "
        parts = re.split(r'\s*(?:;|,|\band\b)\s*', text_to_split, flags=re.IGNORECASE)
        subtask_candidates = [p.strip() for p in parts if len(p.strip()) > 3]

    # If still not broke down, create default phase breakdown templates
    if len(subtask_candidates) <= 1:
        subtask_candidates = [
            f"Research and prepare requirements for {title}",
            f"Execute implementation for {title}",
            f"Review and verify completion of {title}",
        ]

    subtasks = []
    for item in subtask_candidates:
        cap_title = item[0].upper() + item[1:] if item else "Subtask"
        subtasks.append({
            "title": cap_title,
            "description": f"Subtask generated from parent task '{title}': {cap_title}",
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else None,
        })

    return subtasks


def call_llm_parser(text: str, today: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Optional LLM wrapper for natural language task parsing.
    Checks settings.LLM_API_KEY. If missing, raises an exception signaling 503.
    """
    api_key = getattr(settings, 'LLM_API_KEY', None)
    if not api_key:
        raise PermissionError("LLM API key not configured")

    # In future expansion, call Gemini / OpenAI API using api_key
    # For now, falls back to parse_task_text
    return parse_task_text(text, today)
