import os, re, logging
from datetime import datetime
from typing import List, Dict

import telebot
from telebot import types
import types as pytypes
from telebot.handler_backends import StatesGroup, State

from jinja2 import Template
import pdfkit
import html
import time
# =========================
# ЛОГИ
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("kp-bot-branch")

# =========================
# НАСТРОЙКИ
# =========================
TOKEN = os.getenv("TELEGRAM_TOKEN", 'TELEGRAM_TOKEN')

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
path_wkhtmltopdf = r"C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe"

config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

THEME = {"brand": "#2c5aa0", "muted": "#6b7280", "accent": "#10b981"}
EMOJI = {"start": "📝", "about": "ℹ️", "back": "⬅️", "home": "🏠", "ok": "✅", "no": "❌", "edit": "✍️", "confirm": "✔️",
         "info": "📋", "check": "☑️", "empty": "⬜"}

# Сколько опций показывать на одной «странице»

PAGE_SIZE = 5

# =========================
# SAFE EDIT
# =========================
def h(s: str) -> str:
    # безопасное экранирование любого динамического текста
    return html.escape(s or "", quote=False)

def safe_edit_text(chat_id: int, message_id: int, text: str, markup=None):
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except Exception as e:
        s = str(e).lower()
        if "message is not modified" in s:
            return
        if "message to edit not found" in s or "can't be edited" in s:
            bot.send_message(chat_id, text, reply_markup=markup)
            return
        raise

from threading import Timer

def safe_delete(chat_id: int, message_id: int):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def send_temp(chat_id: int, text: str, ttl: int = 5, reply_markup=None):
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
    Timer(ttl, lambda: safe_delete(chat_id, msg.message_id)).start()
    return msg


# =========================
# FSM (используем состояния только для текстовых вводов)
# =========================
class St(StatesGroup):
    name = State()
    org_name = State()
    org_category = State()
    has_site = State()
    has_site_comment = State()
    product = State()
    biz_goal = State()
    audience = State()
    user_action = State()
    contacts = State()
    other_input = State()  # универсальный ввод "Свой вариант"


# =========================
# ВСПОМОГАТЕЛЬНОЕ: РАМКА ДЛЯ ВОПРОСОВ
# =========================
FRAME = "───────────────────────"

def framed(text: str) -> str:
    return f"{text}"

def framed_bottom(text: str) -> str:
    # вариант: вопрос + линия снизу (нужно для одного шага)
    return f"{text}\n{FRAME}"
# =========================
# КНОПКИ
# =========================
def kb(*rows, add_back=False, add_home=False):
    m = types.InlineKeyboardMarkup()
    for row in rows:
        m.row(*row)
    if add_back:
        m.row(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back"))
    return m
def main_menu_kb():
    return kb(
        [types.InlineKeyboardButton(f"{EMOJI['start']} Начать", callback_data="act_start")],
        [types.InlineKeyboardButton(f"{EMOJI['about']} О боте", callback_data="act_about")]
    )


def yn_kb():
    # Да и Нет в столбик
    return kb(
        [types.InlineKeyboardButton(f"{EMOJI['ok']} Да", callback_data="yn_yes")],
        [types.InlineKeyboardButton(f"{EMOJI['no']} Нет", callback_data="yn_no")],
        add_back=True, add_home=True
    )
def yn_kb_all_horizontal():
    back = types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back")
    no   = types.InlineKeyboardButton(f"{EMOJI['no']} Нет", callback_data="yn_no")
    yes  = types.InlineKeyboardButton(f"{EMOJI['ok']} Да", callback_data="yn_yes")
    m = types.InlineKeyboardMarkup()
    m.row(back, no, yes)  # все в одной строке
    return m


# =========================
# ПРОГРЕСС (исправлено: стабильный тотал и единая длина бара)
# =========================

# =========================
# ДАННЫЕ ПОЛЬЗОВАТЕЛЯ
# =========================
USER: Dict[int, dict] = {}  # chat_id -> dict

# Базовые шаги до выбора ветки
BASE_ORDER = [
    "name", "org_name", "has_site", "has_site_comment",
    "biz_goal", "user_action", "product", "solution",
]
COMMON_ORDER = ["design", "content", "timeline", "contacts", "confirm"]

# Ветки
BRANCH_FLOW = {
    # Лендинг / Корпоративный — короткие ветки (по 2 шага)
    "A": ["A1_blocks", "A2_functions"],
    # Интернет-магазин — 3 шага
    "B": ["B1_sections", "B2_assort", "B3_functions"],
    # Чат-бот — 3 шага
    "C": ["C1_tasks", "C2_platforms", "C3_integrations"],
    # Маркетинг — 3 шага
    "D": ["D1_goals", "D2_channels", "D4_budget"],
}
BASE_FLOW   = BASE_ORDER.copy()
COMMON_FLOW = COMMON_ORDER.copy()

BASE_LEN    = len(BASE_ORDER)
BRANCH_MAX  = max(len(v) for v in BRANCH_FLOW.values())  # убедись, что BRANCH_FLOW объявлен выше
COMMON_LEN  = len(COMMON_ORDER)
STABLE_TOTAL= BASE_LEN + BRANCH_MAX + COMMON_LEN

BASE_LEN = len(BASE_ORDER)                              # 8
BRANCH_MAX = max(len(v) for v in BRANCH_FLOW.values()) # 3
COMMON_LEN = len(COMMON_ORDER)                          # 5
STABLE_TOTAL = BASE_LEN + BRANCH_MAX + COMMON_LEN       # 8 + 3 + 5 = 16

def clear_state(ch: int):
    try:
        bot.delete_state(ch)  # сброс активного state у пользователя
    except Exception:
        pass

def init_user(ch: int):
    USER[ch] = {
        "idx": 0,
        "flow": BASE_ORDER.copy(),
        "data": {},
        "branch": None,
        "solution": None,
        "multiselect_ctx": {},
        "last_mid": None,                 # 👈 сюда будем класть id последнего сообщения бота
    }

def get_last_mid(ch: int):
    return USER.get(ch, {}).get("last_mid")

def set_last_mid(ch: int, mid: int | None):
    if ch in USER:
        USER[ch]["last_mid"] = mid

def get_flow(ch: int) -> List[str]:
    return USER[ch]['flow']


def cur_step(ch: int) -> str:
    return get_flow(ch)[USER[ch]['idx']]


def set_step(ch: int, key: str):
    USER[ch]['idx'] = get_flow(ch).index(key)


def next_step(ch: int):
    USER[ch]['idx'] = min(USER[ch]['idx'] + 1, len(get_flow(ch)) - 1)


def total_steps(ch: int) -> int:
    return len(get_flow(ch))

def go_back(ch: int, mid: int | None):
    """
    Единый корректный 'Назад':
    - если пользователь в текстовом режиме текущего шага (biz_goal/user_action/other_input),
      просто выходим из state и перерисовываем текущий шаг (без перехода на предыдущий).
    - иначе: очищаем state и уходим на предыдущий шаг по flow.
    """
    try:
        st = bot.get_state(ch, ch)  # например 'St:biz_goal', 'St:other_input', ...
    except Exception:
        st = None

    st = (st or "").lower()

    # 1) Кастомный ввод по кнопке "Свой вариант" для конкретного шага (мультивыбор)
    if st.endswith(":other_input"):
        step = multiselect_state(ch).get("step") or cur_step(ch)
        clear_state(ch)
        send_step(ch, step, mid=mid, edit=True)
        return

    # 2) Кастомный ввод для "Какую задачу решить" (biz_goal)
    if st.endswith(":biz_goal"):
        clear_state(ch)
        send_step(ch, "biz_goal", mid=mid, edit=True)
        return

    # 3) Кастомный ввод для "Целевое действие" (user_action)
    if st.endswith(":user_action"):
        clear_state(ch)
        send_step(ch, "user_action", mid=mid, edit=True)
        return

    # 4) Остальные текстовые состояния (включая has_site_comment, contacts и т.п.) — идём на предыдущий шаг
    clear_state(ch)
    USER[ch]["idx"] = max(0, USER[ch]["idx"] - 1)
    send_step(ch, cur_step(ch), mid=mid, edit=True)

# =========================
# СТАБИЛЬНЫЙ ТОТАЛ И КАРТА ИНДЕКСОВ ДЛЯ ПРОГРЕССА
# =========================
def _planned_total_const() -> int:
    base_len = len(BASE_FLOW)
    b_max = max(len(v) for v in BRANCH_FLOW.values())
    comm_len = len(COMMON_FLOW)
    return base_len + b_max + comm_len

def progress_for_step(ch: int, step_key: str):
    base_len = len(BASE_FLOW)
    b_max = max(len(v) for v in BRANCH_FLOW.values())
    total = base_len + b_max + len(COMMON_FLOW)

    branch = USER.get(ch, {}).get("branch")
    if not branch:
        # ещё не выбрана ветка — позиция в BASE
        if step_key in BASE_FLOW:
            idx_in_base = BASE_FLOW.index(step_key) + 1
        else:
            # если вызывают для шага за пределами BASE до выбора ветки — безопасный фолбек
            idx_in_base = min(base_len, USER.get(ch, {}).get("idx", 0) + 1)
        return idx_in_base, total

    if step_key in BASE_FLOW:
        return BASE_FLOW.index(step_key) + 1, total

    if step_key in BRANCH_FLOW[branch]:
        i = BRANCH_FLOW[branch].index(step_key) + 1
        sel_len = len(BRANCH_FLOW[branch])
        # хотим: i=1 -> scaled=1 (всегда 9/total), i=sel_len -> scaled=b_max
        if sel_len <= 1:
            scaled = 1
        else:
            scaled = 1 + round((i - 1) * (b_max - 1) / (sel_len - 1))
        return base_len + scaled, total

    if step_key in COMMON_FLOW:
        i = COMMON_FLOW.index(step_key) + 1
        return base_len + b_max + i, total

    # fallback — по текущему положению
    return min(len(get_flow(ch)), get_flow(ch).index(step_key) + 1 if step_key in get_flow(ch) else USER[ch]['idx'] + 1), total


def step_no(ch: int, step_key: str) -> int:
    """Позиция шага в ТЕКУЩЕМ пользовательском маршруте (1..len(flow))."""
    flow = get_flow(ch) if ch in USER else []
    if step_key in flow:
        return flow.index(step_key) + 1
    return USER.get(ch, {}).get("idx", 0) + 1  # безопасный фолбэк

def numbered_title(ch: int, step_key: str, text_html: str) -> str:
    return f"{step_no(ch, step_key)}. {text_html}"

# =========================
# ПРОГРЕСС → СЧЁТЧИК ШАГОВ
# =========================
# единая карта шагов (фрагмент)
STEP_ORDER = [
    "name", "org_name",
    "has_site", "has_site_comment",   # 👈 комментарий = 4/16
    "biz_goal", "user_action", "solution",
    "A1_blocks", "A2_functions",
    "B1_sections", "B2_assort", "B3_functions",
    "C1_tasks", "C2_platforms", "C3_integrations",
    "D1_goals", "D2_channels", "D4_budget",
    "design", "content", "timeline", "contacts", "confirm"
]
STEP_INDEX = {k: i+1 for i, k in enumerate(STEP_ORDER)}
TOTAL_STEPS = len(STEP_ORDER)
def render_for_step(ch: int, step_key: str) -> str:
    return ""  # отключено по требованию: скрыть 1/16 и т.п.

# =========================
# ОПЦИИ ПО ТЗ
# =========================
# A1: лендинг/корпоративный
A1_LANDING = [
    ("hero",      "Главный экран (заголовок)"),
    ("benefits",  "Преимущества / Почему мы"),
    ("contact",   "Форма связи / Контакты"),
    ("gallery",   "Галерея / Портфолио"),
    ("about",     "О нас / О компании"),
    ("products",  "Услуги / продукты"),
    ("reviews",   "Отзывы клиентов"),
]
A1_CORP = [
    ("services",  "Услуги (или каталог услуг)"),
    ("faq",       "FAQ (вопросы и ответы)"),
    ("cases",     "Портфолио / Кейсы"),
    ("prices",    "Цены / Прайс-лист"),
    ("home",      "Главная страница"),
    ("blog",      "Блог / Новости"),
    ("about",     "О компании"),
    ("contacts",  "Контакты"),
    ("team",      "Команда"),
]
A2_FUNCTIONS = [
    ("booking",   "Онлайн-запись / бронирование"),
    ("social",    "Интеграция с соцсетями"),
    ("lk",        "Личный кабинет клиента"),
    ("form",      "Форма обратной связи"),
    ("chat",      "Чат с менеджером"),
]

# B
B1_SECTIONS = [
    ("pdp",       "Страница товара (описание/фото/цена)"),
    ("reviews",   "Отзывы о товарах или магазине"),
    ("home",      "Витрина с акциями/новинками"),
    ("lk",        "Личный кабинет покупателя"),
    ("faq",       "FAQ (вопросы и ответы)"),
    ("about",     "О компании / О нас"),
    ("delivery",  "Доставка и оплата"),
    ("catalog",   "Каталог товаров"),
    ("blog",      "Блог / Статьи"),
    ("contacts",  "Контакты"),
    ("home",      "Главная"),
    ("cart",      "Корзина"),
]
B2_ASSORT = [
    ("m",         "Около 100–200 товаров"),
    ("l",         "Более 200 товаров"),
    ("s",         "До 50 товаров"),
    ("unknown",   "Пока не знаю"),
]
B3_FUNCTIONS = [
    ("fast",      "Оформление заказа в 1 клик"),
    ("filters",   "Фильтры и поиск по товарам"),
    ("lk",        "Личный кабинет покупателя"),
    ("ratings",   "Отзывы и рейтинги"),
    ("compare",   "Сравнение товаров"),
]

# C
C1_TASKS = [
    ("booking_msg",    "Бронирование в мессенджере"),
    ("faq",            "Ответы на вопросы (FAQ)"),
    ("tracking",       "Отслеживание доставки"),
    ("selection",      "Подбор товара / услуг"),
    ("subs_base",      "Сбор базы подписчиков"),
    ("promo",          "Проведение акций"),
    ("record_service", "Запись на услугу"),
    ("record_visit",   "Запись на приём"),
    ("orders",         "Приём заказов"),
    ("status",         "Статус заказа"),
    ("consult",        "Консультации"),
]
C2_PLATFORMS = [
    ("site",           "Сайт (виджет чат-бота)"),
    ("vk",             "ВКонтакте"),
    ("wa",             "WhatsApp"),
    ("tg",             "Telegram"),
    ("vb",             "Viber"),
]
C3_INTEGR = [
    ("crm",      "Интеграция с CRM"),
    ("delivery", "Службы доставки / трекинг"),
    ("db",       "Подключение к базе данных"),
    ("pay",      "Платежные системы"),
    ("ga",       "Подключение аналитики"),
    ("mess",     "Чат или мессенджеры"),
    ("ml",       "Многоязычность"),
]

# D
D1_GOALS = [
    ("audit",          "Понять, что не работает в текущем продвижении (аудит)"),
    ("leads",          "Увеличить поток заявок и продаж (лиды)"),
    ("strategy",       "Разработать долгосрочную стратегию"),
    ("ads_setup",      "Настройка рекламы (Яндекс/Google)"),
    ("brand",          "Повысить узнаваемость бренда"),
    ("seo",            "SEO: улучшить позиции сайта"),
    ("leads",          "Увеличить продажи"),
    ("social",         "Развитие соцсетей"),
    ("ads_manage",     "Ведение рекламы"),
]
D2_CHANNELS = [
    ("seo",                 "Поисковая оптимизация (SEO)"),
    ("ads",                 "Контекстная реклама"),
    ("content_marketing",   "Контент-маркетинг"),
    ("target",              "Таргет в соцсетях"),
    ("email",               "Email-рассылки"),
    ("articles",            "Статьи"),
    ("blog",                "Блог"),
]
D3_CURRENT = [
    ("ads_no_result",       "Есть сайт/реклама(нерезультативно)"),
    ("nothing",             "Ничего нет, начинаем с нуля"),
    ("site_no_ads",         "Есть сайт, но нет рекламы"),
    ("no_site_social",      "Нет сайта, нужна реклама"),
]
D4_BUDGET = [
    ("lt50",                "До 50 000 ₽/мес"),
    ("50-100",              "50 000–100 000 ₽/мес"),
    ("gt100",               "Более 100 000 ₽/мес"),
    ("advise",              "Предложите оптимальный вариант"),
]
# Общие
DESIGN = [
    ("tpl",            "Готовый шаблон"),
    ("uniq",           "Уникальный дизайн"),
    ("advise",         "Посоветуйте оптимальный вариант")
]
CONTENT = [
    ("client",        "Вы предоставите готовый контент"),
    ("help",          "Помощь с созданием контента"),
    ("mix",           "Смешанный вариант")
]

def _optmap(options):
    return {k: v for k, v in options}

LABELS = {
    # A
    "A1_blocks": (_optmap(A1_LANDING) | _optmap(A1_CORP)),
    "A2_functions": _optmap(A2_FUNCTIONS),

    # B
    "B1_sections": _optmap(B1_SECTIONS),
    "B2_assort": _optmap(B2_ASSORT),
    "B3_functions": _optmap(B3_FUNCTIONS),

    # C
    "C1_tasks": _optmap(C1_TASKS),
    "C2_platforms": _optmap(C2_PLATFORMS),
    "C3_integrations": _optmap(C3_INTEGR),

    # D
    "D4_budget": {
        "lt50": "До 50 000 ₽/мес",
        "50-100": "50 000–100 000 ₽/мес",
        "gt100": "Более 100 000 ₽/мес",
        "advise": "Предложите оптимальный вариант",
    },

    # Общие
    "design": _optmap(DESIGN),
    "content": _optmap(CONTENT),
    "timeline": {
        "1-2w": "1–2 недели",
        "2-4w": "2–4 недели",
        "1-2m": "1–2 месяца",
        "2-4m": "2–4 месяца",
    },
}

def humanize_list(step: str, keys: list[str]) -> list[str]:
    mp = LABELS.get(step, {})
    return [mp.get(k, k) for k in (keys or [])]

def humanize_dict(step: str, dct: dict | None) -> str:
    """Из {'items':[...],'other':...} делает маркированный HTML со «человеческими» подписями."""
    if not dct:
        return ""
    items = humanize_list(step, dct.get("items", []))
    if dct.get("other"):
        items.append(f"Другое: {dct['other']}")
    return "<br>• " + "<br>• ".join(items) if items else ""




# =========================
# МУЛЬТИВЫБОР с пагинацией
# =========================
def multiselect_state(ch: int):
    """Гарантированно вернуть словарь контекста мультивыбора."""
    ctx = USER[ch].get("multiselect_ctx")
    if not isinstance(ctx, dict):
        ctx = {"step": None, "selected": set(), "single": False, "preset": None, "page": 0}
        USER[ch]["multiselect_ctx"] = ctx
    ctx.setdefault("step", None)
    ctx.setdefault("selected", set())
    ctx.setdefault("single", False)
    ctx.setdefault("preset", None)
    ctx.setdefault("page", 0)
    return ctx


def start_multiselect(ch: int, step: str, single: bool = False, preset: List[str] = None, seed: List[str] = None):
    ctx = multiselect_state(ch)
    ctx["step"] = step
    ctx["single"] = single
    ctx["preset"] = preset or []
    ctx["selected"] = set(seed or [])
    ctx["page"] = 0  # всегда начинаем с первой страницы


def ensure_multiselect(ch: int, step: str, single: bool = False):
    """
    Инициализируем контекст ТОЛЬКО при первом входе в шаг.
    Если выбор ранее сохранён — подхватываем его, не сбрасывая галочки.
    """
    ctx = multiselect_state(ch)
    if ctx["step"] != step:
        prev_items = USER[ch]["data"].get(step, {}).get("items", [])
        start_multiselect(ch, step, single=single, seed=prev_items)
    else:
        ctx["single"] = single  # синхронизируем режим

from telebot import types

def bottom_row_for_step(step: str, add_back=True, add_other=False, add_done=False):
    row = []
    if add_back:
        row.append(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back"))
    if add_other:
        row.append(types.InlineKeyboardButton("📝 Свой вариант", callback_data=f"other::{step}"))
    if add_done:
        row.append(types.InlineKeyboardButton("✅ Готово", callback_data=f"done::{step}"))
    return row

def toggle_select(ch: int, key: str):
    ctx = multiselect_state(ch)
    if ctx["single"]:
        ctx["selected"] = set([key])
    else:
        if key in ctx["selected"]:
            ctx["selected"].remove(key)
        else:
            ctx["selected"].add(key)


def set_other_value(ch: int, text: str):
    d = USER[ch]["data"]
    step = multiselect_state(ch)["step"]
    d.setdefault(step, {"items": [], "other": None})
    d[step]["other"] = text


def save_multiselect(ch: int):
    ctx = multiselect_state(ch)
    d = USER[ch]["data"]
    d[ctx["step"]] = {"items": list(ctx["selected"]), "other": d.get(ctx["step"], {}).get("other")}
    return d[ctx["step"]]


def selected_marker(ch: int, key: str) -> str:
    return EMOJI['check'] if key in multiselect_state(ch)["selected"] else EMOJI['empty']


def build_paginated_rows(ch: int, step: str, options, page: int,
                         add_other_text: str = None, add_preset: bool = False):
    rows = []
    start = page * PAGE_SIZE
    end = min(len(options), start + PAGE_SIZE)

    # Основные опции — всегда в столбик
    for key, label in options[start:end]:
        btn = types.InlineKeyboardButton(
            f"{selected_marker(ch, key)} {label}",
            callback_data=f"opt::{step}::{key}"
        )
        rows.append([btn])

    # Пагинация
    if page > 0:
        rows.append([types.InlineKeyboardButton("◀️ Предыдущие варианты", callback_data=f"page::{step}::{page-1}")])
    if end < len(options):
        rows.append([types.InlineKeyboardButton("Еще варианты ▶️", callback_data=f"page::{step}::{page+1}")])

    # Пресет — отдельной строкой
    if add_preset:
        rows.append([types.InlineKeyboardButton("Предложите стандартный набор",
                                                callback_data=f"preset::{step}")])
    # «Свой вариант» + «Готово» — в одну строку
    if add_other_text:
        other_btn = types.InlineKeyboardButton(add_other_text, callback_data=f"other::{step}")
        done_btn  = types.InlineKeyboardButton("Готово", callback_data=f"done::{step}")
        rows.append([other_btn, done_btn])
    else:
        rows.append([types.InlineKeyboardButton("Готово", callback_data=f"done::{step}")])

    return rows

def kb_with_bottom(rows, back=False, other_cd=None, done_cd=None, other_text="📝 Свой вариант", done_text="✅ Готово"):
    m = types.InlineKeyboardMarkup()
    for r in rows:
        m.row(*r)
    bottom = []
    if back:
        bottom.append(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back"))
    if other_cd:
        bottom.append(types.InlineKeyboardButton(other_text, callback_data=other_cd))
    if done_cd:
        bottom.append(types.InlineKeyboardButton(done_text, callback_data=done_cd))
    if bottom:
        m.row(*bottom)
    return m

def pretty_human(step: str, entry) -> str:
    """Переводит коды в русские подписи через LABELS."""
    if not entry:
        return "—"
    if isinstance(entry, dict) and "items" in entry:
        items = humanize_list(step, entry["items"])
        text = ", ".join(items)
        if entry.get("other"):
            text += f"; Другое: {entry['other']}"
        return text
    return str(entry)

def multiselect_screen(ch: int, step: str, title_html: str, options,
                       single: bool = False, add_other_text: str = None, add_preset: bool = False):
    ensure_multiselect(ch, step, single=single)
    page = multiselect_state(ch)["page"]

    rows = build_paginated_rows(
        ch, step, options, page,
        add_other_text=add_other_text, add_preset=add_preset
    )

    # достанем из rows «Свой вариант» и «Готово», чтобы собрать их вместе с «Назад»
    other_btn = None
    done_btn = None
    for r in rows:
        for btn in list(r):
            cd = getattr(btn, "callback_data", "") or ""
            if cd.startswith("other::") and other_btn is None:
                other_btn = btn
                r.remove(btn)
            elif cd.startswith("done::") and done_btn is None:
                done_btn = btn
                r.remove(btn)

    # нижний общий ряд (⬅ Назад | 📝 Свой вариант | ✅ Готово)
    bottom = bottom_row_for_step(
        step,
        add_back=True,
        add_other=(other_btn is not None),
        add_done=(done_btn is not None),
    )

    # (кнопки «Назад» у нас фиксированные, «Свой вариант/Готово» мог быть кастомным по стилю)
    if other_btn is not None:
        bottom[1] = other_btn  # на месте «Свой вариант»
    if done_btn is not None:
        bottom[-1] = done_btn  # на месте «Готово»

    rows.append(bottom)

    m = types.InlineKeyboardMarkup()
    for r in rows:
        if r:
            m.row(*r)

    text = f"{render_for_step(ch, step)}{framed(f'<b>{title_html}</b>')}"
    return text, m

# =========================
# ТЕКСТ ПОМОЩИ/ОПИСАНИЯ
# =========================
SERVICES_INFO = (
    "<b>Описание услуг:</b>\n\n"
    "• <b>Лендинг</b> — одностраничный сайт для быстрых продаж и заявок.\n"
    "• <b>Интернет-магазин</b> — каталог, корзина, оплата и доставка.\n"
    "• <b>Корпоративный сайт</b> — разделы о компании, услугах, кейсах.\n"
    "• <b>Чат-бот</b> — автоматизация ответов/заявок.\n"
    "• <b>Маркетинг</b> — SEO и контекстная реклама."
)


# =========================
# РЕНДЕР ШАГОВ (со стилем «в рамке») — ВСЕ КНОПКИ В СТОЛБИК + ПАГИНАЦИЯ
# =========================
def send_step(ch: int, step_key: str, mid: int = None, edit: bool = False):
    flow = get_flow(ch)

    # локальный алиас нумерации: всегда подставляет ch
    def NT(step: str, text_html: str) -> str:
        return numbered_title(ch, step, text_html)

    def _send(text, markup=None):
        if edit and mid:
            try:
                safe_edit_text(ch, mid, text, markup)
                set_last_mid(ch, mid)
                return
            except Exception:
                pass
        m = bot.send_message(ch, text, reply_markup=markup)
        set_last_mid(ch, m.message_id)

    # ===== БАЗОВЫЕ =====
    if step_key == 'name':
        bot.set_state(ch, St.name, ch)
        title = NT('name', '<b>Представьтесь пожалуйста, как Вас зовут?</b>')
        _send(f"{render_for_step(ch, 'name')}{framed(title)}\n")
        return

    if step_key == 'org_name':
        bot.set_state(ch, St.org_name, ch)
        title = NT('org_name', '<b>Как называется ваша организация?</b>')
        _send(f"{render_for_step(ch, 'org_name')}{framed(title)}", kb(add_back=True, add_home=True))
        return

    if step_key == 'org_category':
        bot.set_state(ch, St.org_category, ch)
        title = NT('org_category', '<b>Выберите категорию вашей организации:</b>')
        _send(
            f"{render_for_step(ch, 'org_category')}{framed(title)}",
            kb(
                [types.InlineKeyboardButton("Юридическое лицо", callback_data="cat_ul")],
                [types.InlineKeyboardButton("Физическое лицо", callback_data="cat_fl")],
                [types.InlineKeyboardButton("ИП", callback_data="cat_ip")],
                add_back=True, add_home=True
            )
        )
        return

    if step_key == 'has_site':
        clear_state(ch)
        bot.set_state(ch, St.has_site, ch)
        title = NT('has_site', '<b>У вас уже есть сайт?</b>')
        _send(f"{render_for_step(ch, 'has_site')}{framed(title)}", yn_kb_all_horizontal())
        return

    if step_key == 'product':
        bot.set_state(ch, St.product, ch)
        title = NT('product', '<b>Какой продукт или услугу Вы планируете продвигать?</b>')
        _send(f"{render_for_step(ch, 'product')}{framed(title)}", kb(add_back=True, add_home=True))
        return

    if step_key == 'biz_goal':
        clear_state(ch)
        title = NT('biz_goal', '<b>Какую главную задачу должен решить сайт?</b>')
        _send(
            f"{render_for_step(ch, 'biz_goal')}{framed(title)}",
            kb_with_bottom(
                rows=[
                    [types.InlineKeyboardButton("Информировать о товарах, услугах", callback_data="goal_info2")],
                    [types.InlineKeyboardButton("Информировать о деятельности", callback_data="goal_info")],
                    [types.InlineKeyboardButton("Повышать узнаваемость бренда", callback_data="goal_brand")],
                    [types.InlineKeyboardButton("Продавать товары или услуги", callback_data="goal_sell")],
                    [types.InlineKeyboardButton("Собирать заявки", callback_data="goal_leads")],
                ],
                back=True,
                other_cd="goal_custom"
            )
        )
        return

    if step_key == 'audience':
        bot.set_state(ch, St.audience, ch)
        title = NT('audience', '<b>Кто Ваши потенциальные клиенты?</b>')
        _send(
            f"{render_for_step(ch, 'audience')}{framed_bottom(title)}\n"
            "Напишите пол, возраст, род деятельности или интересы.\n\n"
            "<i>Например: «женщины; 25–40 лет; интересующиеся модой».</i>\n",
            kb(add_back=True)
        )
        return

    if step_key == 'user_action':
        clear_state(ch)
        title = NT('user_action', '<b>Какое целевое действие должен совершить пользователь на сайте?</b>')
        _send(
            f"{render_for_step(ch, 'user_action')}{framed(title)}",
            kb_with_bottom(
                rows=[
                    [types.InlineKeyboardButton("Оставить заявку", callback_data="act_lead")],
                    [types.InlineKeyboardButton("Подписаться", callback_data="act_sub")],
                    [types.InlineKeyboardButton("Позвонить", callback_data="act_call")],
                    [types.InlineKeyboardButton("Купить", callback_data="act_buy")],
                ],
                back=True,
                other_cd="act_custom"
            )
        )
        return

    if step_key == 'solution':
        clear_state(ch)
        info = (
            "───────────────────────\n"
            "<b>Описание услуг:</b>\n\n"
            "• <b>Маркетинг</b> — SEO и контекстная реклама.\n"
            "• <b>Корпоративный сайт</b> — разделы о компании, услугах, кейсах.\n"
            "• <b>Интернет-магазин</b> — каталог, корзина, оплата и доставка.\n"
            "• <b>Лендинг</b> — одностраничный сайт для быстрых продаж и заявок.\n"
            "• <b>Чат-бот</b> — автоматизация ответов/заявок."
        )
        title = NT('solution', '<b>Какое решение вам нужно?</b>')
        text = f"{render_for_step(ch, 'solution')}{framed(title)}\n{info}"
        _send(
            text,
            kb(
                [types.InlineKeyboardButton("Маркетинг (SEO/контекст)", callback_data="sol_mkt")],
                [types.InlineKeyboardButton("Корпоративный сайт", callback_data="sol_corp")],
                [types.InlineKeyboardButton("Интернет-магазин", callback_data="sol_shop")],
                [types.InlineKeyboardButton("Лендинг", callback_data="sol_land")],
                [types.InlineKeyboardButton("Чат-бот", callback_data="sol_bot")],
                add_back=True
            )
        )
        return

    # ===== ВЕТКИ/ОБЩИЕ =====
    if step_key == 'A1_blocks':
        clear_state(ch)
        sol = USER[ch]["solution"]
        opts = A1_LANDING if sol == "Лендинг" else A1_CORP
        t_html = NT('A1_blocks', '<b>Выберите ключевые блоки/разделы:</b>')
        text, markup = multiselect_screen(
            ch, 'A1_blocks', t_html,
            opts, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'A2_functions':
        clear_state(ch)
        t_html = NT('A2_functions', '<b>Планируете ли Вы функционал на сайте?</b>')
        text, markup = multiselect_screen(
            ch, 'A2_functions', t_html,
            A2_FUNCTIONS, single=False, add_other_text="📝 Свой вариант"
        )
        _send(text, markup); return

    if step_key == 'B1_sections':
        clear_state(ch)
        t_html = NT('B1_sections', '<b>Разделы интернет-магазина:</b>')
        text, markup = multiselect_screen(
            ch, 'B1_sections', t_html,
            B1_SECTIONS, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'B2_assort':
        clear_state(ch)
        t_html = NT('B2_assort', '<b>Сколько примерно товаров планируете?</b>')
        text, markup = multiselect_screen(
            ch, 'B2_assort', t_html,
            B2_ASSORT, single=True
        )
        _send(text, markup); return

    if step_key == 'B3_functions':
        clear_state(ch)
        t_html = NT('B3_functions', '<b>Какой функционал нужен в магазине, кроме корзины?</b>')
        text, markup = multiselect_screen(
            ch, 'B3_functions', t_html,
            B3_FUNCTIONS, single=False
        )
        _send(text, markup); return

    if step_key == 'C1_tasks':
        clear_state(ch)
        t_html = NT('C1_tasks', '<b>Где чат-бот принесёт максимальную пользу?</b>')
        text, markup = multiselect_screen(
            ch, 'C1_tasks', t_html,
            C1_TASKS, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'C2_platforms':
        clear_state(ch)
        t_html = NT('C2_platforms', '<b>В каких мессенджерах/платформах должен работать чат-бот?</b>')
        text, markup = multiselect_screen(
            ch, 'C2_platforms', t_html,
            C2_PLATFORMS, single=False, add_other_text="📝 Свой вариант"
        )
        _send(text, markup); return

    if step_key == 'C3_integrations':
        clear_state(ch)
        t_html = NT('C3_integrations', '<b>Нужны ли Вам интеграции с внешними сервисами?</b>')
        text, markup = multiselect_screen(
            ch, 'C3_integrations', t_html,
            C3_INTEGR, single=False
        )
        _send(text, markup); return

    if step_key == 'D1_goals':
        clear_state(ch)
        t_html = NT('D1_goals', '<b>Какую задачу хотите решить маркетингом?</b>')
        text, markup = multiselect_screen(
            ch, 'D1_goals', t_html,
            D1_GOALS, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'D2_channels':
        clear_state(ch)
        t_html = NT('D2_channels', '<b>Какие каналы продвижения хотите использовать?</b>')
        text, markup = multiselect_screen(
            ch, 'D2_channels', t_html,
            D2_CHANNELS, single=False
        )
        _send(text, markup); return

    if step_key == 'D4_budget':
        clear_state(ch)
        t_html = NT('D4_budget', '<b>Какой примерный бюджет на маркетинг планируете ежемесячно?</b>')
        text, markup = multiselect_screen(
            ch, 'D4_budget', t_html,
            D4_BUDGET, single=True
        )
        _send(text, markup); return

    if step_key == 'design':
        clear_state(ch)
        t_html = NT('design', '<b>Какой дизайн Вы хотите?</b>')
        text, markup = multiselect_screen(ch, 'design', t_html, DESIGN, single=True)
        _send(text, markup); return

    if step_key == 'content':
        clear_state(ch)
        t_html = NT('content', '<b>Кто предоставляет контент материалы?</b>')
        text, markup = multiselect_screen(ch, 'content', t_html, CONTENT, single=True)
        _send(text, markup); return

    if step_key == 'timeline':
        clear_state(ch)
        sol = USER[ch]["solution"]
        if sol in ("Лендинг", "Чат-бот", "Маркетинг (SEO/контекст)"):
            opts = [("1-2w", "1–2 недели"), ("2-4w", "2–4 недели")]
        elif sol == "Корпоративный сайт":
            opts = [("2-4w", "2–4 недели"), ("1-2m", "1–2 месяца")]
        elif sol == "Интернет-магазин":
            opts = [("1-2m", "1–2 месяца"), ("2-4m", "2–4 месяца")]
        else:
            opts = []
        t_html = NT('timeline', '<b>Как быстро нужно выполнить работу?</b>')
        text, markup = multiselect_screen(ch, 'timeline', t_html, opts, single=True)
        _send(text, markup); return

    if step_key == 'contacts':
        clear_state(ch)
        bot.set_state(ch, St.contacts, ch)
        frame = "───────────────────────"
        head = NT('contacts', '<b>Благодарю Вас за ответы. Оставьте контактные данные:</b>')
        body_html = (
            f"{frame}\n{head}\n{frame}\n"
            "• 📧 Почта\n"
            "• 📱 Телефон\n"
            "• 💬 @username\n\n"
            "<i>Можете ввести любые контактные данные текстом.</i>"
        )
        _send(
            f"{render_for_step(ch, 'contacts')}{body_html}",
            kb([types.InlineKeyboardButton("📱 Поделиться контактом", callback_data="share_contact")],
               add_back=True, add_home=True)
        )
        return

    if step_key == 'confirm':
        d = USER[ch]["data"]
        tl_code = (d.get("timeline") or {}).get("items", [None])
        if isinstance(tl_code, list): tl_code = tl_code[0]
        tl_label = LABELS["timeline"].get(tl_code, "—")
        design_text = ", ".join(humanize_list("design", (d.get("design") or {}).get("items", []))) or "—"
        content_text = ", ".join(humanize_list("content", (d.get("content") or {}).get("items", []))) or "—"
        budget_text = LABELS["D4_budget"].get((d.get("D4_budget") or {}).get("items", [None])[0], "—")

        name = d.get("name", "—")
        s = [
            f"<b>Имя:</b> {name}",
            f"<b>Организация:</b> {d.get('org_name', '—')}",
            f"<b>Есть сайт:</b> {d.get('has_site', '—')}",
        ]
        if d.get("has_site_comment"):
            s.append(f"<b>Комментарий к сайту:</b> {d.get('has_site_comment')}")
        s += [
            f"<b>Продукт/услуга:</b> {d.get('product', '—')}",
            f"<b>Бизнес-задача:</b> {d.get('biz_goal', '—')}",
            f"<b>ЦА:</b> {d.get('audience', '—')}",
            f"<b>Целевое действие:</b> {d.get('user_action', '—')}",
            f"<b>Тип решения:</b> {USER[ch].get('solution','—')}",
            f"<b>Дизайн:</b> {design_text}",
            f"<b>Контент:</b> {content_text}",
            f"<b>Бюджет:</b> {budget_text}",
            f"<b>Сроки:</b> {tl_label}",
            f"<b>Контакты:</b> {d.get('contacts', '—')}",
        ]
        title = NT('confirm', '<b>Проверьте данные:</b>')
        _send(
            f"{render_for_step(ch, 'confirm')}{framed(title)}\n" + "\n".join(s),
            kb([types.InlineKeyboardButton(f"{EMOJI['confirm']} Скачать КП (PDF)", callback_data="go_pdf")],
               add_home=True)
        )
        return

# =========================
# ХЭЛПЕР ДЛЯ ВЫВОДА
# =========================
def pretty_items(entry):
    if not entry:
        return "—"
    if isinstance(entry, dict) and "items" in entry:
        items = entry["items"]
        text = ", ".join(items)
        return text + (f"; Другое: {entry.get('other')}" if entry.get("other") else "")
    return str(entry)


# =========================
# PDF
# =========================
KP_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"><title>Коммерческое предложение</title>
<style>
 body{font-family:Arial,sans-serif;margin:40px;line-height:1.6;color:#333}
 .header{text-align:center;margin-bottom:32px;border-bottom:2px solid #2c5aa0;padding-bottom:14px}
 .header h1{color:#2c5aa0;margin:0 0 8px}
 .muted{color:#6b7280}
 .section{margin-bottom:28px}
 .section-title{font-weight:bold;font-size:20px;margin:10px 0 12px;color:#2c5aa0;padding-bottom:6px;border-bottom:2px solid #2c5aa0}
 .kv{display:grid;grid-template-columns:220px 1fr;gap:8px 16px}
 .item{margin:6px 0}
 .subsection{margin:8px 0 10px}
 .subsection-title{font-weight:bold;color:#2c5aa0;margin-bottom:6px}
 table{width:100%;border-collapse:collapse;margin-top:10px}
 th,td{border:1px solid #e5e7eb;padding:10px;text-align:left}
 th{background:#2c5aa0;color:#fff}
 .total{font-size:20px;font-weight:bold;margin-top:12px;padding:12px;background:#f8f9fa;border-left:4px solid #2c5aa0}
 .contact-info{background:#e8f4ff;padding:16px;border-radius:8px}
</style>
</head>
<body>

<div class="header">
  <h1>Коммерческое предложение</h1>
  <div class="muted"><b>Дата:</b> {{ date }}</div>
</div>

{% if client.org_name or client.org_category %}
<div class="section">
  <div class="section-title">Клиент</div>
  <div class="kv">
    {% if client.org_name %}<div><b>Компания:</b></div><div>{{ client.org_name }}</div>{% endif %}
    {% if client.org_category %}<div><b>Статус:</b></div><div>{{ client.org_category }}</div>{% endif %}
  </div>
</div>
{% endif %}

<div class="section">
  <div class="section-title">Обзор проекта</div>
  <div class="kv">
    <div><b>Решение:</b></div><div>{{ project.site_type }}</div>
    {% if project.goal %}<div><b>Цель:</b></div><div>{{ project.goal }}</div>{% endif %}
    {% if project.audience %}<div><b>Целевая аудитория:</b></div><div>{{ project.audience }}</div>{% endif %}
  </div>
  {% if project.has_site %}<div class="item"><b>Наличие сайта:</b> {{ project.has_site }}</div>{% endif %}
  {% if project.has_site_comment %}<div class="item"><b>Комментарий к сайту:</b> {{ project.has_site_comment }}</div>{% endif %}
</div>

{% if selections_title and selections_text %}
<div class="section">
  <div class="section-title">{{ selections_title }}</div>
  {{ selections_text }}
</div>
{% endif %}

<div class="section">
  <div class="section-title">Параметры</div>
  <div class="kv">
    {% if common.design %}<div><b>Дизайн:</b></div><div>{{ common.design }}</div>{% endif %}
    {% if common.content %}<div><b>Контент:</b></div><div>{{ common.content }}</div>{% endif %}
    {% if common.integr %}<div><b>Интеграции:</b></div><div>{{ common.integr }}</div>{% endif %}
    {% if common.timeline %}<div><b>Сроки:</b></div><div>{{ common.timeline }}</div>{% endif %}
    {% if budget %}<div><b>Бюджет (маркетинг):</b></div><div>{{ budget }}</div>{% endif %}
  </div>
</div>

{% if options and options|length %}
<div class="section">
  <div class="section-title">Дополнительные опции</div>
  <table>
    <tr><th>Опция</th><th>Стоимость</th></tr>
    {% for o in options %}
      <tr>
        <td>{{ o.name }}</td>
        <td>{% if o.price == 'manager' %}<span style="color:#e74c3c;">Уточняется у менеджера</span>{% else %}{{ o.price }} ₽{% endif %}</td>
      </tr>
    {% endfor %}
  </table>
</div>
{% endif %}

<div class="section">
  <div class="section-title">Стоимость</div>
  <div class="item"><b>Базовая стоимость:</b> {{ base_price }} ₽</div>
  <div class="total">Итоговая стоимость: {{ total_price }} ₽</div>
  {% if dev_time %}<div class="item"><b>Срок разработки:</b> {{ dev_time }}</div>{% endif %}
</div>

<div class="section contact-info">
  <div class="section-title">Контакты</div>
  <div class="item"><b>Для связи:</b> {{ client.contacts }}</div>
  <div class="item">Менеджер свяжется с вами в течение 24 часов</div>
</div>

</body></html>
"""




# Базовые цены по типу решения
BASE_PRICES = {
    "Лендинг": 180000,
    "Корпоративный сайт": 150000,
    "Интернет-магазин": 240000,
    "Чат-бот": 120000,
    "Маркетинг (SEO/контекст)": 0,
}

# Номенклатура опций (можно расширять — это даёт таблицу как на скрине)
OPTION_PRICES = {
    "Техническая поддержка (1 месяц)": 5000,
    "SEO-базовая оптимизация": 27000,
    "Интеграция эквайринга": 36000,
    "Система доставки": 36000,
    "Система онлайн-записи": 27000,
    "Интеграция с соцсетями": 18000,
    "Мультивалютность": 14400,
    "Фирменный стиль": "manager",
}

def _human(v):
    return pretty_items(v) if isinstance(v, (dict, list)) else (v or "—")

def _lines_from_dict(dct: dict|None) -> str:
    """Преобразует словарь вида {'items':[...],'other':...} в маркированные строки."""
    if not dct or "items" not in dct: return ""
    parts = dct["items"][:]
    if dct.get("other"): parts.append(f"Другое: {dct['other']}")
    return "<br>• " + "<br>• ".join(parts) if parts else ""

def build_kp_context(ch: int):
    d = USER[ch]["data"]
    site_type = USER[ch].get("solution", "—")

    # --- 2.1 Человекочитаемые списки по ветке ---
    parts = []
    # подбираем только актуальные группы под выбранное решение
    if site_type in ("Лендинг", "Корпоративный сайт"):
        for key, title in [("A1_blocks","Блоки/разделы"), ("A2_functions","Функционал сайта")]:
            if d.get(key):
                html_block = humanize_dict(key, d[key])
                if html_block:
                    parts.append(f"<div class='subsection'><div class='subsection-title'>{title}</div>{html_block}</div>")
        selections_title = "Структура и функционал сайта"

    elif site_type == "Интернет-магазин":
        for key, title in [("B1_sections","Разделы магазина"), ("B3_functions","Функции магазина")]:
            if d.get(key):
                html_block = humanize_dict(key, d[key])
                if html_block:
                    parts.append(f"<div class='subsection'><div class='subsection-title'>{title}</div>{html_block}</div>")
        selections_title = "Структура и функционал магазина"

    elif site_type == "Чат-бот":
        for key, title in [("C1_tasks","Задачи чат-бота"), ("C2_platforms","Платформы"), ("C3_integrations","Интеграции бота")]:
            if d.get(key):
                html_block = humanize_dict(key, d[key])
                if html_block:
                    parts.append(f"<div class='subsection'><div class='subsection-title'>{title}</div>{html_block}</div>")
        selections_title = "Задачи и платформы чат-бота"

    else:  # Маркетинг (SEO/контекст) — показываем цели и каналы
        for key, title in [("D1_goals","Цели маркетинга"), ("D2_channels","Каналы продвижения")]:
            if d.get(key):
                html_block = humanize_dict(key, d[key])
                if html_block:
                    parts.append(f"<div class='subsection'><div class='subsection-title'>{title}</div>{html_block}</div>")
        selections_title = "Цели и каналы маркетинга"

    selections_text = "".join(parts)


    # соберём «синие» блоки
    selections_text_parts = []
    for key, title in [
        ("A1_blocks", "Блоки/разделы"),
        ("A2_functions", "Функционал сайта"),
        ("B1_sections", "Разделы магазина"),
        ("B3_functions", "Функции магазина"),
        ("C1_tasks", "Задачи чат-бота"),
        ("C2_platforms", "Платформы"),
        ("C3_integrations", "Интеграции бота"),
    ]:
        if d.get(key):
            lines = humanize_dict(key, d[key])  # 👈 вместо _lines_from_dict
            if lines:
                selections_text_parts.append(
                    f"<div class='subsection'><div class='subsection-title'>{title}</div>{lines}</div>"
                )
    selections_text = "".join(selections_text_parts)

    # базовая цена
    base_price = BASE_PRICES.get(site_type, 0)

    # опции (пример: добавим несколько типовых — можно наращивать маппинг как потребуется)
    options = []
    for name, price in OPTION_PRICES.items():
        # покажем те, что логически связаны с выбранными шагами пользователя
        if name == "Система онлайн-записи" and 'A2_functions' in d and 'booking' in d['A2_functions'].get('items', []):
            options.append({"name": name, "price": price})
        elif name == "Интеграция с соцсетями" and (
            ('A2_functions' in d and 'social' in d['A2_functions'].get('items', [])) or
            ('C3_integrations' in d and 'mess' in d['C3_integrations'].get('items', []))
        ):
            options.append({"name": name, "price": price})
        elif name in ("SEO-базовая оптимизация","Техническая поддержка (1 месяц)","Фирменный стиль","Интеграция эквайринга","Система доставки","Мультивалютность"):
            # пока добавим их всегда как пример (чтобы таблица выглядела как на эталонном скрине)
            options.append({"name": name, "price": price})

    # сумма по опциям (исключая «manager»)
    total_opts = sum(x["price"] for x in options if isinstance(x["price"], (int,float)))
    total_price = base_price + total_opts
    has_manager_options = any(x["price"] == "manager" for x in options)

    # сроки: из мультивыбора 'timeline' приходит код ('1-2w'/'2-4w'/'1-2m'/'2-4m')
    tl_code = (d.get("timeline") or {}).get("items", [None])
    if isinstance(tl_code, list):  # single-select хранится как список из одного кода
        tl_code = tl_code[0]

    timeline_map = {
        "1-2w": "1–2 недели",
        "2-4w": "2–4 недели",
        "1-2m": "1–2 месяца",
        "2-4m": "2–4 месяца",
    }
    tl_label = timeline_map.get(tl_code, "—")  # <-- теперь всегда определена

    # человекочитаемая длительность разработки для PDF
    dev_time = {
        "1–2 недели": "14 дней",
        "2–4 недели": "28 дней",
        "1–2 месяца": "1–2 месяца",
        "2–4 месяца": "2–4 месяца",
    }.get(tl_label, tl_label or "—")
    ctx = {
        "date": datetime.now().strftime("%d.%m.%Y"),
        "client": {
            "name": d.get("name", "—"),
            "org_name": d.get("org_name", "—"),
            "org_category": d.get("org_category", ""),
            "contacts": d.get("contacts", "—"),
        },
        "project": {
            "site_type": site_type,
            "goal": d.get("biz_goal", ""),
            "audience": d.get("audience", ""),
            "has_site": d.get("has_site", ""),
            "has_site_comment": d.get("has_site_comment", ""),
        },
        "common": {
            "design": pretty_human("design", d.get("design")),
            "content": pretty_human("content", d.get("content")),
            "integr": pretty_human("C3_integrations", d.get("C3_integrations")),
            "timeline": tl_label,
        },
        "budget": pretty_human("D4_budget", d.get("D4_budget")),   # пустое не покажется в шаблоне
        "selections_title": selections_title if selections_text else "",
        "selections_text": selections_text,
        "options": options,
        "base_price": base_price,
        "total_price": total_price,
        "dev_time": dev_time or "",
        "has_manager_options": has_manager_options,
    }
    return ctx


def render_branch_for_pdf(d: dict, solution: str):
    out = {}
    if 'A1_blocks' in d: out["Блоки/разделы"] = pretty_items(d['A1_blocks'])
    if 'A2_functions' in d: out["Функционал"] = pretty_items(d['A2_functions'])
    if 'B1_sections' in d: out["Разделы магазина"] = pretty_items(d['B1_sections'])
    if 'B2_assort' in d: out["Ассортимент"] = pretty_items(d['B2_assort'])
    if 'B3_functions' in d: out["Функционал магазина"] = pretty_items(d['B3_functions'])
    if 'C1_tasks' in d: out["Задачи чат-бота"] = pretty_items(d['C1_tasks'])
    if 'C2_platforms' in d: out["Платформы"] = pretty_items(d['C2_platforms'])
    if 'C3_integrations' in d: out["Интеграции бота"] = pretty_items(d['C3_integrations'])
    if 'D1_goals' in d: out["Цели маркетинга"] = pretty_items(d['D1_goals'])
    if 'D2_channels' in d: out["Каналы"] = pretty_items(d['D2_channels'])
    if 'D3_current' in d: out["Текущая ситуация"] = pretty_items(d['D3_current'])
    if 'D4_budget' in d: out["Бюджет"] = pretty_items(d['D4_budget'])
    return out

def make_kp_html(ch: int) -> str:
    ctx = build_kp_context(ch)                           # уже есть в коде
    html_text = Template(KP_TEMPLATE).render(**ctx)      # KP_TEMPLATE уже есть

    out_dir = os.path.join(os.getcwd(), "generated_kp")
    os.makedirs(out_dir, exist_ok=True)

    raw_contacts = USER[ch]["data"].get("contacts", "")  # вытаскиваем телефон
    phone = re.sub(r"\D", "", raw_contacts) or "unknown"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")     # дата+время, чтобы не перезатирать
    out_path = os.path.join(out_dir, f"KP_{phone}_{stamp}.html")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return out_path

def make_pdf(ch: int) -> str:
    # теперь PDF не генерим, возвращаем путь к HTML
    return make_kp_html(ch)

# =========================
# ПОТОК/ВЕТКИ
# =========================
def apply_branch_flow(ch: int, solution_label: str):
    USER[ch]["solution"] = solution_label
    USER[ch]["multiselect_ctx"] = {}

    if solution_label in ("Лендинг", "Корпоративный сайт"):
        b = 'A'
    elif solution_label == "Интернет-магазин":
        b = 'B'
    elif solution_label == "Чат-бот":
        b = 'C'
    else:
        b = 'D'
    USER[ch]["branch"] = b

    # добираем ветку к ТЕКУЩЕМУ маршруту (в котором «has_site_comment» уже
    # есть или его нет – в зависимости от ответа пользователя)
    flow = USER[ch]["flow"]
    if "solution" in flow:
        prefix = flow[:flow.index("solution") + 1]
    else:
        prefix = flow[:]
    USER[ch]["flow"] = prefix + BRANCH_FLOW[b] + COMMON_ORDER
    USER[ch]["idx"] = USER[ch]["flow"].index("solution")
# =========================
# CALLBACK-и
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "share_contact")
def on_share_contact(c):
    ch = c.message.chat.id
    bot.answer_callback_query(c.id)

    share_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    share_kb.add(types.KeyboardButton("📱 Отправить мой номер", request_contact=True))

    send_temp(
        ch,
        "👇 Нажмите кнопку «📱 Отправить мой номер» ниже.\n"
        "Я автоматически добавлю ваш номер телефона и Telegram-ник в контакты КП.",
        ttl=6,
        reply_markup=share_kb
    )

@bot.message_handler(content_types=['contact'], state=St.contacts)
def in_contact_obj(m):
    ch = m.chat.id
    parsed = parse_contacts("", tg_username=m.from_user.username,
                            phone_from_share=(m.contact.phone_number if m.contact else None))
    USER[ch]["data"]["contacts"] = format_contacts(parsed)
    safe_delete(ch, m.message_id)          # 🗑️ удалить сообщение с «поделиться контактом»
    send_temp(ch, "✅ Контакт добавлен!", ttl=3, reply_markup=types.ReplyKeyboardRemove())
    next_step(ch)
    send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

@bot.callback_query_handler(func=lambda c: True)
def on_cb(c):
    ch, mid, data = c.message.chat.id, c.message.message_id, c.data

    # 👇 защита: если чата ещё нет в памяти, создаём
    if ch not in USER:
        init_user(ch)

    set_last_mid(ch, mid)

    if data == "ui_back":
        go_back(ch, mid)
        return
    try:
        bot.answer_callback_query(c.id)
    except Exception:
        pass
    log.info(
        f"cb:{data} idx={USER.get(ch, {}).get('idx')} step={USER.get(ch, {}).get('flow', [None])[USER.get(ch, {}).get('idx', 0)] if USER.get(ch) else '—'}")

    try:
        if data == "act_start":
            init_user(ch)
            send_step(ch, 'name', mid, edit=True)
            return
        if data == "act_about":
            about_text = (
                "ℹ️ <b>О боте</b>\n\n"
                "1) Отвечаете на вопросы (≈3–5 минут).\n"
                "2) Выбираете решение и нужные опции.\n"
                "3) Получаете готовое КП в PDF.\n\n"
                "<b>Конфиденциальность</b>\n"
                "Ответы используются только для формирования КП и связи с вами.\n\n"
                "Если возникнут вопросы — нажмите «Связаться с менеджером» ниже."
            )
            about_kb = types.InlineKeyboardMarkup()
            about_kb.add(types.InlineKeyboardButton("📝 Начать", callback_data="act_start"))
            about_kb.add(types.InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/PlaBarov"))
            safe_edit_text(ch, mid, about_text, about_kb)
            return

        if data == "ui_home":
            safe_edit_text(ch, mid, "Главное меню:", main_menu_kb())
            return
        if data == "ui_back":
            go_back(ch, mid)
            return
        # категории
        if data.startswith("cat_"):
            USER[ch]["data"]["org_category"] = \
                {"cat_fl": "Физическое лицо", "cat_ip": "ИП", "cat_ul": "Юридическое лицо", "cat_other": "Свой вариант"}[
                    data]
            next_step(ch)
            send_step(ch, cur_step(ch), mid, edit=True)
            return

        # есть сайт?
        if data in ("yn_yes", "yn_no") and cur_step(ch) == "has_site":
            USER[ch].setdefault("data", {})["has_site"] = "Да" if data == "yn_yes" else "Нет"

            if data == "yn_yes":
                # короткий маршрут: комментарий → контакты → подтверждение
                USER[ch]["flow"] = ["name", "org_name", "has_site", "has_site_comment", "contacts", "confirm"]
                set_step(ch, "has_site_comment")
                bot.set_state(ch, St.has_site_comment, ch)
                prompt = framed(
                    numbered_title(ch, 'has_site_comment',
                                   "<b>Что вам нравится в вашем сайте, и что бы вы хотели изменить?</b>")
                    + "\n<i>Например: «нравится дизайн, но нет корзины».</i>"
                )
                safe_edit_text(
                    ch, mid,
                    f"{render_for_step(ch, 'has_site_comment')}{prompt}",
                    kb([types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data='ui_back')])
                )
            else:
                # полный маршрут: задача → действие → продукт → решение ...
                USER[ch]["flow"] = ["name", "org_name", "has_site", "biz_goal", "user_action", "product", "solution"]
                set_step(ch, "biz_goal")
                send_step(ch, "biz_goal", mid, edit=True)
            return

        # goal buttons
        if data.startswith("goal_"):
            mm = {"goal_sell": "Продавать товары или услуги", "goal_leads": "Собирать заявки",
                  "goal_info2": "Информировать о товарах или услугах",
                  "goal_info": "Информировать о деятельности",
                  "goal_brand": "Повышать узнаваемость бренда"}
            if data == "goal_custom":
                bot.set_state(ch, St.biz_goal, ch)  # <-- state только здесь
                safe_edit_text(
                    ch, mid,
                    f"{render_for_step(ch, 'biz_goal')}{framed(numbered_title(ch, 'biz_goal', 'Опишите вашу ключевую задачу текстом:'))}",
                    kb(add_back=True, add_home=True)
                )
            else:
                USER[ch]["data"]["biz_goal"] = mm[data]
                next_step(ch)
                send_step(ch, cur_step(ch), mid, edit=True)
            return

        # user action buttons
        if data.startswith("act_"):
            mm = {"act_buy": "Купить", "act_call": "Позвонить", "act_lead": "Оставить заявку", "act_sub": "Подписаться"}
            if data == "act_custom":
                bot.set_state(ch, St.user_action, ch)
                safe_edit_text(
                    ch, mid,
                    f"{render_for_step(ch, 'user_action')}{framed(numbered_title(ch, 'user_action', 'Укажите нужное действие текстом:'))}",
                    kb(add_back=True, add_home=True)
                )
            else:
                USER[ch]["data"]["user_action"] = mm[data]
                next_step(ch)
                send_step(ch, cur_step(ch), mid, edit=True)
            return

        # solution + info
        if data.startswith("sol_"):
            label = {"sol_land": "Лендинг", "sol_shop": "Интернет-магазин", "sol_corp": "Корпоративный сайт",
                     "sol_bot": "Чат-бот", "sol_mkt": "Маркетинг (SEO/контекст)"}[data]
            apply_branch_flow(ch, label)
            next_step(ch)  # перейти на первый шаг ветки
            send_step(ch, cur_step(ch), mid, edit=True)
            return

        # ==== мультивыбор ====
        if data.startswith("opt::"):
            _, step, key = data.split("::", 2)
            toggle_select(ch, key)
            send_step(ch, step, mid, edit=True)
            return

        if data.startswith("done::"):
            _, step = data.split("::", 1)
            save_multiselect(ch)
            next_step(ch)
            send_step(ch, cur_step(ch), mid, edit=True)
            return

        if data.startswith("other::"):
            _, step = data.split("::", 1)
            multiselect_state(ch)["step"] = step
            bot.set_state(ch, St.other_input, ch)
            safe_edit_text(
                ch, mid,
                f"{render_for_step(ch, step)}{framed(numbered_title(ch, step, 'Напишите ваш вариант текстом:'))}",
                kb(add_back=True, add_home=True)
            )
            return

        if data.startswith("preset::"):
            _, step = data.split("::", 1)
            # пресеты
            if step == "A1_blocks":
                sol = USER[ch]["solution"]
                preset = [k for k, _ in (A1_LANDING if sol == "Лендинг" else A1_CORP)][:4]
            elif step == "B1_sections":
                preset = ["home", "catalog", "pdp", "cart", "contacts"]
            elif step == "C1_tasks":
                preset = ["faq", "consult", "booking"]
            elif step == "D1_goals":
                preset = ["leads", "seo"]
            else:
                preset = []
            start_multiselect(ch, step, single=False, seed=preset)
            send_step(ch, step, mid, edit=True)
            return

        # смена страницы
        if data.startswith("page::"):
            _, step, page_s = data.split("::", 2)
            st = multiselect_state(ch)
            st["step"] = step
            st["page"] = max(0, int(page_s))
            send_step(ch, step, mid, edit=True)
            return

        # pdf
        if data in ("go_pdf", "go_kp"):
            try:
                path = make_kp_html(ch)  # или make_pdf(ch) — без разницы, оба дадут HTML
                with open(path, "rb") as f:
                    bot.send_document(
                        ch, f,
                        visible_file_name=os.path.basename(path),
                        caption="Готово ✅ (HTML)"
                    )
            except Exception as e:
                log.error(f"make_kp_html failed: {e}")
                bot.send_message(ch, "Не удалось сформировать файл. Сообщите менеджеру, пожалуйста.")
            return

    except Exception:
        log.exception("callback error")


# =========================
# ТЕКСТОВЫЕ ВВОДЫ
# =========================
CONTACT_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CONTACT_TG_RE    = re.compile(r"@[A-Za-z0-9_]{5,32}")
CONTACT_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{6,}\d")

def _normalize_phone(s: str) -> str | None:
    if not s: return None
    digits = re.sub(r"\D", "", s)
    if not digits: return None
    # нормализуем РФ-формат типа 8XXXXXXXXXX → +7XXXXXXXXXX
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return ("+" + digits) if not digits.startswith("+") else digits

def parse_contacts(text: str | None, tg_username: str | None = None, phone_from_share: str | None = None) -> dict:
    """Достаём email/telegram/phone из текста + из системных полей"""
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

    # из системных полей, если пользователь нажал «Поделиться контактом»
    if phone_from_share and "phone" not in res:
        p = _normalize_phone(phone_from_share)
        if p: res["phone"] = p

    if tg_username and "telegram" not in res and tg_username:
        nick = tg_username if tg_username.startswith("@") else f"@{tg_username}"
        res["telegram"] = nick

    return res

def format_contacts(c: dict | None) -> str:
    if not c: return "—"
    parts = []
    if c.get("phone"):    parts.append(f"Телефон {c['phone']}")
    if c.get("email"):    parts.append(f"Email {c['email']}")
    if c.get("telegram"): parts.append(f"Telegram {c['telegram']}")
    return "; ".join(parts)

@bot.message_handler(commands=['start'])
def on_start(m):
    init_user(m.chat.id)
    # ⚠️ Если фото по пути отсутствует — закомментируйте блок ниже
    try:
        with open("C:/Users/Maksim/Documents/Платон/chat bot/бот КП/фото.jpg", "rb") as photo:
            bot.send_photo(m.chat.id, photo)
    except Exception:
        pass

    m = bot.send_message(
        m.chat.id,
        "👋 <b>Здравствуйте!  Меня зовут Ева!</b>\n\n"
        "Я помогу Вам создать сайт\n"
        "или настроить продвижение!\n\n"
        "Давайте начнем с нескольких вопросов.",
        reply_markup=main_menu_kb()
    )
    set_last_mid(m.chat.id, m.message_id)


from threading import Timer

@bot.message_handler(state=St.name)
@bot.message_handler(state=St.name)
def in_name(m):
    ch = m.chat.id
    name = (m.text or "").strip()
    USER[ch]["data"]["name"] = name
    safe_delete(ch, m.message_id)          # 🗑️ удалить ответ
    next_step(ch)

    # показываем краткое приветствие тем же сообщением бота
    safe_edit_text(ch, get_last_mid(ch), f"Рада нашему знакомству, <b>{h(name)}</b>!")

    from threading import Timer
    Timer(2, lambda: send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)).start()


@bot.message_handler(state=St.org_name)
def in_org_name(m):
    ch = m.chat.id
    t = (m.text or "").strip()
    safe_delete(ch, m.message_id)          # 🗑️
    if len(t) < 2:
        # краткое системное напоминание (исчезнет при следующем редактировании)
        bot.send_message(ch, "❌ Введите название организации.")
        return
    USER[ch]["data"]["org_name"] = t
    next_step(ch)
    send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)


@bot.message_handler(state=St.has_site_comment)
def in_site_comment(m):
    ch = m.chat.id
    USER[ch]["data"]["has_site_comment"] = (m.text or "").strip()
    safe_delete(ch, m.message_id)

    # Гарантируем, что в пользовательском потоке есть контакты и подтверждение
    flow = get_flow(ch)
    extra = []
    if "contacts" not in flow:
        extra.append("contacts")
    if "confirm" not in flow:
        extra.append("confirm")
    if extra:
        USER[ch]["flow"] = flow + extra

    # Переходим на шаг 'contacts' и показываем экран на месте текущего сообщения бота
    USER[ch]["idx"] = USER[ch]["flow"].index("contacts")
    clear_state(ch)
    send_step(ch, "contacts", mid=get_last_mid(ch), edit=True)

@bot.message_handler(state=St.product)
def in_product(m):
    ch = m.chat.id
    USER[ch]["data"]["product"] = (m.text or "").strip()
    safe_delete(ch, m.message_id)          # 🗑️
    next_step(ch)
    send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)


@bot.message_handler(state=St.biz_goal)
def in_goal(m):
    ch = m.chat.id
    USER[ch]["data"]["biz_goal"] = (m.text or "").strip()
    safe_delete(ch, m.message_id)          # 🗑️
    next_step(ch)
    send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)


@bot.message_handler(state=St.audience)
def in_aud(m):
    ch = m.chat.id
    USER[ch]["data"]["audience"] = (m.text or "").strip()
    safe_delete(ch, m.message_id)          # 🗑️
    next_step(ch)
    send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)


@bot.message_handler(state=St.user_action)
def in_act(m):
    ch = m.chat.id
    USER[ch]["data"]["user_action"] = (m.text or "").strip()
    safe_delete(ch, m.message_id)          # 🗑️
    next_step(ch)
    send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)


@bot.message_handler(state=St.other_input)
def in_other(m):
    ch = m.chat.id
    set_other_value(ch, (m.text or "").strip())
    safe_delete(ch, m.message_id)          # 🗑️
    step = USER[ch]["multiselect_ctx"]["step"]
    send_step(ch, step, mid=get_last_mid(ch), edit=True)

@bot.message_handler(state=St.contacts)
def in_contacts(m):
    ch, txt = m.chat.id, (m.text or "").strip()
    parsed = parse_contacts(txt, m.from_user.username)
    safe_delete(ch, m.message_id)  # не копим текст пользователя

    if not parsed:
        send_temp(ch, "❌ Введите email, телефон (цифрами) или @username.", ttl=6)
        return

    USER[ch]["data"]["contacts"] = format_contacts(parsed)
    send_temp(ch, "✅ Контакт добавлен!", ttl=5)
    next_step(ch)
    send_step(ch, cur_step(ch), mid=USER[ch].get("last_mid"), edit=True)

@bot.message_handler(func=lambda m: True)
def fallback(m):
    ch = m.chat.id
    # удаляем произвольный текст пользователя, чтобы не копился «хвост»
    safe_delete(ch, m.message_id)
    if ch not in USER:
        on_start(m)
    # иначе — ничего не делаем: активный вопрос редактируется в одном сообщении

# =========================
# RUN
# =========================
if __name__ == "__main__":
    print("Bot is running…")
    bot.add_custom_filter(telebot.custom_filters.StateFilter(bot))
    bot.infinity_polling()
