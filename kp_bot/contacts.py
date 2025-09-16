"""
contacts.py

Обработка контактов/заявок пользователя и подготовка данных для PDF.
(Файл аннотирован автоматически; логика не изменена.)
"""


import re
from .utils import send_temp

CONTACT_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CONTACT_TG_RE    = re.compile(r"@[A-Za-z0-9_]{5,32}")
CONTACT_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{6,}\d")

# [auto]: функция _normalize_phone()
def _normalize_phone(s: str) -> str | None:
    if not s: return None
    digits = re.sub(r"\D", "", s)
    if not digits: return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return ("+" + digits) if not digits.startswith("+") else digits

# [auto]: функция parse_contacts()
def parse_contacts(text: str | None, tg_username: str | None = None, phone_from_share: str | None = None) -> dict:
    res = {}
    t = text or ""

    m = CONTACT_EMAIL_RE.search(t)
    if m: res["email"] = m.group(0)

    m = CONTACT_TG_RE.search(t)
    if m: res["telegram"] = m.group(0)

    m = CONTACT_PHONE_RE.search(t)
    if m:
        p = _normalize_phone(m.group(0))
        if p: res["phone"] = p

    if phone_from_share and "phone" not in res:
        p = _normalize_phone(phone_from_share)
        if p: res["phone"] = p

    if tg_username and "telegram" not in res and tg_username:
        nick = tg_username if tg_username.startswith("@") else f"@{tg_username}"
        res["telegram"] = nick

    return res

# [auto]: функция format_contacts()
def format_contacts(c: dict | None) -> str:
    if not c: return "—"
    parts = []
    if c.get("phone"):    parts.append(f"Телефон {c['phone']}")
    if c.get("email"):    parts.append(f"Email {c['email']}")
    if c.get("telegram"): parts.append(f"Telegram {c['telegram']}")
    return "; ".join(parts)