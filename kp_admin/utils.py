# kp_admin/utils.py
from __future__ import annotations
import re
import html as ihtml
from typing import Optional

# Телефон: допускаем пробелы/скобки/дефисы, берём 10–15 цифр
PHONE_RE = re.compile(
    r"(?:тел(?:ефон)?\s*[:\-]?\s*)?(\+?\d[\d\-\s().]{7,}\d)",
    flags=re.IGNORECASE | re.UNICODE,
)

# Telegram username: '@name' или 'Telegram @name'
USERNAME_RE = re.compile(
    r"(?:telegram\s*@|телеграм\s*@|@)([A-Za-z0-9_]{3,32})",
    flags=re.IGNORECASE | re.UNICODE,
)

BAD_USERNAMES = {"mail", "email", "почта", "none", "нет"}


def _strip_tags(html: str) -> str:
    """Грубое удаление тегов + unescape + схлопывание пробелов."""
    text = ihtml.unescape(html)
    text = re.sub(r"<[^>]+>", " ", text)        # убрать теги
    text = re.sub(r"\s+", " ", text).strip()    # схлопнуть пробелы
    return text


def _normalize_phone(raw: str) -> Optional[str]:
    """Оставляем только цифры, приводим RU-номера к +7, валидируем длину."""
    if not raw:
        return None
    digits = re.sub(r"\D+", "", raw)
    if not digits:
        return None

    # Частые случаи
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]           # 8XXXXXXXXXX -> 7XXXXXXXXXX
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits               # 9XXXXXXXXX  -> 79XXXXXXXXX

    # Допустимая длина международного номера
    if not (10 <= len(digits) <= 15):
        return None

    if not digits.startswith(("7", "8", "9", "1", "2", "3", "4", "5", "6")):
        # если что-то экзотическое — всё равно вернём с плюсом
        pass

    # финально добавляем +
    if not digits.startswith("+"):
        digits = "+" + digits
    return digits


def _sanitize_username(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip().lstrip("@")
    if not u:
        return None
    if u.lower() in BAD_USERNAMES:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", u):
        return None
    return u


def parse_kp_file_meta(path: str) -> dict:
    """
    Читает HTML-КП и пытается достать метаданные.
    Возвращает dict: {phone, username, name?, chat_id?}
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="cp1251", errors="ignore") as f:
            raw = f.read()

    text = _strip_tags(raw)

    # Телефон
    phone = None
    m = PHONE_RE.search(text)
    if m:
        phone = _normalize_phone(m.group(1))

    # Username
    username = None
    mu = USERNAME_RE.search(text)
    if mu:
        username = _sanitize_username(mu.group(1))

    # Имя клиента (если хочешь — можно расширить по своим шаблонам)
    name = None
    # пример: "Клиент: Иван" или "Имя: …"
    mn = re.search(r"(?:Клиент|Имя)\s*[:\-]\s*([A-Za-zА-Яа-яЁё0-9_ \-]{2,50})", text)
    if mn:
        name = mn.group(1).strip()

    return {
        "phone": phone,
        "username": username,
        "name": name,
        # "chat_id": можно доставать, если ты где-то его пишешь в HTML
    }
