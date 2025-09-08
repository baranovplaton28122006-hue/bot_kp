import os, re, logging
from datetime import datetime
from typing import List, Dict

import telebot
from telebot import types
from telebot.handler_backends import StatesGroup, State

from jinja2 import Template
import pdfkit

# =========================
# ЛОГИ
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("kp-bot-branch")

# =========================
# НАСТРОЙКИ
# =========================
TOKEN = os.getenv("TELEGRAM_TOKEN", '8068452070:AAFLDvT5HMKOQfhK5tcOD1zAJfmP84cmAvI')
if not TOKEN:
    log.warning("⚠️ TELEGRAM_TOKEN не задан (export TELEGRAM_TOKEN=...)")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
WKHTML = r"C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe" if os.name == "nt" else "/usr/bin/wkhtmltopdf"

THEME = {"brand": "#2c5aa0", "muted": "#6b7280", "accent": "#10b981"}
EMOJI = {"start": "📝", "about": "ℹ️", "back": "⬅️", "home": "🏠", "ok": "✅", "no": "❌", "edit": "✍️", "confirm": "✔️",
         "info": "📋", "check": "☑️", "empty": "⬜"}

# Сколько опций показывать на одной «странице»
PAGE_SIZE = 6

# =========================
# SAFE EDIT
# =========================
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
def framed(text: str) -> str:
    frame = "───────────────────────"
    return f"{frame}\n{text}\n{frame}"


# =========================
# КНОПКИ
# =========================
def kb(*rows, add_back=False, add_home=False):
    m = types.InlineKeyboardMarkup()
    for row in rows:
        m.row(*row)
    # управляющие кнопки — всегда в одну строку
    if add_back or add_home:
        btns = []
        if add_back:
            btns.append(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back"))
        if add_home:
            btns.append(types.InlineKeyboardButton(f"{EMOJI['home']} В меню", callback_data="ui_home"))
        m.row(*btns)
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


# =========================
# ПРОГРЕСС
# =========================
def render_progress(done: int, total: int) -> str:
    pct = int(done * 100 / max(1, total))
    filled = min(20, max(1, pct // 5))
    bar = "🟩" * filled + "⬛" * (15 - filled)
    return f"<b>{bar} {pct}%</b>\n"


# =========================
# ДАННЫЕ ПОЛЬЗОВАТЕЛЯ
# =========================
USER: Dict[int, dict] = {}  # chat_id -> dict

# Базовые шаги до выбора ветки
BASE_FLOW = ['name', 'org_name', 'org_category', 'has_site', 'product', 'biz_goal', 'audience', 'user_action',
             'solution']

# Ветки
BRANCH_FLOW = {
    'A': ['A1_blocks', 'A2_functions'],  # Landing/Corp
    'B': ['B1_sections', 'B2_assort', 'B3_functions'],  # Shop
    'C': ['C1_tasks', 'C2_platforms', 'C3_integrations'],  # Bot
    'D': ['D1_goals', 'D2_channels', 'D3_current', 'D4_budget']  # Marketing
}
COMMON_FLOW = ['design', 'content', 'integrations_common', 'timeline', 'contacts', 'confirm']


def init_user(ch: int):
    USER[ch] = {
        "idx": 0,
        "flow": BASE_FLOW.copy(),
        "data": {},
        "branch": None,  # 'A'/'B'/'C'/'D'
        "solution": None,  # human label
        # контекст мультивыбора — всегда словарь
        "multiselect_ctx": {}
    }


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


# =========================
# ОПЦИИ ПО ТЗ
# =========================
# A1: лендинг/корпоративный
A1_LANDING = [
    ("hero", "Главный экран (заголовок, призыв к действию)"),
    ("about", "О нас / О компании"),
    ("products", "Услуги или продукты"),
    ("benefits", "Преимущества / Почему мы"),
    ("gallery", "Галерея / Портфолио"),
    ("reviews", "Отзывы клиентов"),
    ("contact", "Форма связи / Контакты"),
]
A1_CORP = [
    ("home", "Главная страница"),
    ("about", "О компании"),
    ("services", "Услуги (или каталог услуг)"),
    ("cases", "Портфолио / Кейсы"),
    ("blog", "Блог / Новости"),
    ("contacts", "Контакты"),
    ("team", "Команда"),
    ("prices", "Цены / Прайс-лист"),
    ("faq", "FAQ (вопросы и ответы)"),
]
A2_FUNCTIONS = [
    ("form", "Форма обратной связи"),
    ("booking", "Онлайн-запись / бронирование"),
    ("chat", "Чат с менеджером"),
    ("social", "Интеграция с соцсетями"),
    ("lk", "Личный кабинет клиента"),
]

# B
B1_SECTIONS = [
    ("home", "Главная (витрина с акциями, новинками)"),
    ("catalog", "Каталог товаров"),
    ("pdp", "Страница товара (описание, фото, цена)"),
    ("cart", "Корзина"),
    ("lk", "Личный кабинет покупателя"),
    ("about", "О компании / О нас"),
    ("delivery", "Доставка и оплата"),
    ("contacts", "Контакты"),
    ("reviews", "Отзывы о товарах или магазине"),
    ("blog", "Блог / Статьи"),
    ("faq", "FAQ (вопросы и ответы)"),
]
B2_ASSORT = [("s", "До 50 товаров"), ("m", "Около 100–200 товаров"), ("l", "Более 200 товаров"),
             ("unknown", "Пока не знаю")]
B3_FUNCTIONS = [
    ("filters", "Фильтры и поиск по товарам"),
    ("ratings", "Отзывы и рейтинги"),
    ("compare", "Сравнение товаров"),
    ("fast", "Оформление заказа в 1 клик (онлайн-оплата)"),
    ("lk", "Личный кабинет покупателя"),
]

# C
C1_TASKS = [
    ("consult", "Консультации и подбор товара/услуги"),
    ("booking", "Прием заказов или бронирование в мессенджере"),
    ("promo", "Проведение акций и сбор базы подписчиков"),
    ("faq", "Ответы на частые вопросы (FAQ)"),
    ("status", "Информация о статусе заказа или отслеживание доставки"),
    ("record", "Запись на услугу или прием"),
]
C2_PLATFORMS = [("tg", "Telegram"), ("wa", "WhatsApp"), ("vb", "Viber"), ("vk", "ВКонтакте"),
                ("site", "Сайт (виджет чат-бота)")]
C3_INTEGR = [
    ("crm", "Интеграция с CRM (Битрикс24, AmoCRM)"),
    ("pay", "Платежные системы"),
    ("delivery", "Службы доставки / трекинг"),
    ("db", "Подключение к базе данных"),
]

# D
D1_GOALS = [
    ("leads", "Увеличить поток заявок и продаж (лиды)"),
    ("brand", "Повысить узнаваемость бренда"),
    ("seo", "Улучшить позиции сайта в поисковиках (SEO)"),
    ("ads", "Настроить и вести рекламу (Яндекс/Google)"),
    ("social", "Развивать соцсети (Instagram, VK, Telegram)"),
    ("audit", "Понять, что не работает в текущем продвижении (аудит)"),
    ("strategy", "Разработать долгосрочный план (стратегия)"),
]
D2_CHANNELS = [
    ("seo", "Поисковая оптимизация (SEO)"),
    ("ads", "Контекстная реклама"),
    ("target", "Таргет в соцсетях"),
    ("content", "Контент-маркетинг (блог/статьи)"),
    ("email", "Email-маркетинг (рассылки)"),
]
D3_CURRENT = [
    ("site_no_ads", "Есть сайт, но нет рекламы"),
    ("ads_no_result", "Есть сайт и реклама, но результаты не устраивают"),
    ("no_site_social", "Нет сайта, нужна реклама в соцсетях или поисковиках"),
    ("nothing", "Ничего нет, начинаем с нуля"),
]
D4_BUDGET = [("lt50", "До 50 000 ₽/мес"), ("50-100", "50 000–100 000 ₽/мес"), ("gt100", "Более 100 000 ₽/мес"),
             ("advise", "Предложите оптимальный вариант")]

# Общие
DESIGN = [("uniq", "Уникальный дизайн"), ("tpl", "Готовый шаблон"), ("advise", "Посоветуйте оптимальный вариант")]
CONTENT = [("client", "Я предоставлю готовый контент"), ("help", "Нужна помощь с созданием контента"),
           ("mix", "Смешанный вариант")]
INTEGR_COMMON = [("crm", "Интеграция с CRM"), ("ga", "Подключение аналитики"), ("mess", "Чат или мессенджеры"),
                 ("ml", "Многоязычность")]


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



def multiselect_screen(ch: int, step: str, title_html: str, options,
                       single: bool = False, add_other_text: str = None, add_preset: bool = False):
    ensure_multiselect(ch, step, single=single)
    page = multiselect_state(ch)["page"]
    rows = build_paginated_rows(ch, step, options, page,
                                add_other_text=add_other_text, add_preset=add_preset)

    # Перестраиваем нижний ряд: ⬅ Назад | 📝 Свой вариант | ✅ Готово
    back_btn = types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back")
    if rows:
        last = rows[-1]
        has_other = any((getattr(btn, "callback_data", "") or "").startswith("other::") for btn in last)
        has_done  = any((getattr(btn, "callback_data", "") or "").startswith("done::")  for btn in last)
        if has_other or has_done:
            rows[-1] = [back_btn] + last
        else:
            rows.append([back_btn])
    else:
        rows = [[back_btn]]

    m = types.InlineKeyboardMarkup()
    for r in rows:
        m.row(*r)

    text = f"{framed(f'<b>{title_html}</b>')}"
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
    "• <b>Маркетинг</b> — SEO и контекстная рекеклама."
)


# =========================
# РЕНДЕР ШАГОВ (со стилем «в рамке») — ВСЕ КНОПКИ В СТОЛБИК + ПАГИНАЦИЯ
# =========================
def send_step(ch: int, step_key: str, mid: int = None, edit: bool = False):
    flow = get_flow(ch)
    idx = flow.index(step_key)
    done = idx + 1
    total = len(flow)

    def _send(text, markup=None):
        if edit and mid:
            try:
                safe_edit_text(ch, mid, text, markup)
            except Exception:
                bot.send_message(ch, text, reply_markup=markup)
        else:
            bot.send_message(ch, text, reply_markup=markup)

    # ===== БАЗОВЫЕ =====
    if step_key == 'name':
        bot.set_state(ch, St.name, ch)
        _send(
            f"{render_progress(done, total)}{framed('<b>Как Вас зовут?</b>')}\n",
            kb([types.InlineKeyboardButton(f"{EMOJI['home']} В меню", callback_data='ui_home')])
        )
        return

    if step_key == 'org_name':
        bot.set_state(ch, St.org_name, ch)
        nm = USER[ch]["data"].get("name", "")
        title = framed(
            f"Рада нашему знакомству, <b>{nm}</b>!\n\n"
            f"<b>Как называется ваша организация?</b>"
        )
        _send(
            f"{render_progress(done, total)}{title}",
            kb(add_back=True, add_home=True)
        )
        return

    if step_key == 'org_category':
        bot.set_state(ch, St.org_category, ch)
        _send(
            f"{render_progress(done, total)}{framed('<b>Выберите категорию вашей организации:</b>')}",
            kb(
                [types.InlineKeyboardButton("Физическое лицо", callback_data="cat_fl")],
                [types.InlineKeyboardButton("Юридическое лицо", callback_data="cat_ul")],
                [types.InlineKeyboardButton("ИП", callback_data="cat_ip")],
                add_back=True, add_home=True
            )
        )
        return

    if step_key == 'has_site':
        bot.set_state(ch, St.has_site, ch)
        _send(f"{render_progress(done, total)}{framed('<b>У вас уже есть сайт?</b>')}", yn_kb())
        return

    if step_key == 'product':
        bot.set_state(ch, St.product, ch)
        _send(
            f"{render_progress(done, total)}{framed('<b>Какой продукт или услугу вы планируете продвигать?</b>')}",
            kb(add_back=True, add_home=True)
        )
        return

    if step_key == 'biz_goal':
        bot.set_state(ch, St.biz_goal, ch)
        _send(
            f"{render_progress(done, total)}{framed('<b>Какую главную задачу должен решить сайт?</b>')}",
            kb(
                [types.InlineKeyboardButton("Продавать товары или услуги", callback_data="goal_sell")],
                [types.InlineKeyboardButton("Собирать заявки", callback_data="goal_leads")],
                [types.InlineKeyboardButton("Информировать о деятельности, товарах, услугах",
                                            callback_data="goal_info")],
                [types.InlineKeyboardButton("Повышать узнаваемость бренда", callback_data="goal_brand")],
                [types.InlineKeyboardButton("📝 Свой вариант", callback_data="goal_custom")],
                add_back=True, add_home=True
            )
        )
        return

    if step_key == 'audience':
        bot.set_state(ch, St.audience, ch)
        _send(
            f"{render_progress(done, total)}{framed('<b>Кто Ваши потенциальные клиенты?</b>')}\n"
            "Напишите пол, возраст, род деятельности или интересы.\n\n"
            "<i>Например: «женщины; 25–40 лет; интересующиеся модой».</i>\n",
            kb(add_back=True, add_home=True)
        )
        return

    if step_key == 'user_action':
        bot.set_state(ch, St.user_action, ch)
        _send(
            f"{render_progress(done, total)}"
            f"{framed('<b>Какое целевое действие должен совершить пользователь на сайте?</b>')}",
            kb(
                [types.InlineKeyboardButton("Купить", callback_data="act_buy")],
                [types.InlineKeyboardButton("Позвонить", callback_data="act_call")],
                [types.InlineKeyboardButton("Оставить заявку", callback_data="act_lead")],
                [types.InlineKeyboardButton("Подписаться", callback_data="act_sub")],
                [types.InlineKeyboardButton("📝 Свой вариант", callback_data="act_custom")],
                add_back=True, add_home=True
            )
        )
        return

    if step_key == 'solution':
        _send(
            f"{render_progress(done, total)}{framed('<b>Какое решение вам нужно?</b>')}",
            kb(
                [types.InlineKeyboardButton("Лендинг", callback_data="sol_land")],
                [types.InlineKeyboardButton("Интернет-магазин", callback_data="sol_shop")],
                [types.InlineKeyboardButton("Корпоративный сайт", callback_data="sol_corp")],
                [types.InlineKeyboardButton("Чат-бот", callback_data="sol_bot")],
                [types.InlineKeyboardButton("Маркетинг (SEO/контекст)", callback_data="sol_mkt")],
                [types.InlineKeyboardButton(f"{EMOJI['info']} Описание услуг", callback_data="sol_info")],
                add_back=True, add_home=True
            )
        )
        return

    # ===== ВЕТКИ/ОБЩИЕ — через универсальный экран =====
    if step_key == 'A1_blocks':
        sol = USER[ch]["solution"]
        opts = A1_LANDING if sol == "Лендинг" else A1_CORP
        text, markup = multiselect_screen(
            ch, 'A1_blocks', 'Выберите ключевые блоки/разделы (мультивыбор):',
            opts, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'A2_functions':
        text, markup = multiselect_screen(
            ch, 'A2_functions', 'Планируете ли вы функционал на сайте? (мультивыбор)',
            A2_FUNCTIONS, single=False, add_other_text="📝 Свой вариант"
        )
        _send(text, markup); return

    if step_key == 'B1_sections':
        text, markup = multiselect_screen(
            ch, 'B1_sections', 'Разделы интернет-магазина (мультивыбор):',
            B1_SECTIONS, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'B2_assort':
        text, markup = multiselect_screen(
            ch, 'B2_assort', 'Сколько примерно товаров планируете? (один вариант)',
            B2_ASSORT, single=True
        )
        _send(text, markup); return

    if step_key == 'B3_functions':
        text, markup = multiselect_screen(
            ch, 'B3_functions', 'Какой функционал нужен в магазине, кроме корзины? (мультивыбор)',
            B3_FUNCTIONS, single=False
        )
        _send(text, markup); return

    if step_key == 'C1_tasks':
        text, markup = multiselect_screen(
            ch, 'C1_tasks', 'Где чат-бот принесёт максимальную пользу? (мультивыбор)',
            C1_TASKS, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'C2_platforms':
        text, markup = multiselect_screen(
            ch, 'C2_platforms', 'В каких мессенджерах/платформах должен работать чат-бот?',
            C2_PLATFORMS, single=False, add_other_text="📝 Свой вариант"
        )
        _send(text, markup); return

    if step_key == 'C3_integrations':
        text, markup = multiselect_screen(
            ch, 'C3_integrations', 'Нужны ли Вам интеграции с внешними сервисами?',
            C3_INTEGR, single=False
        )
        _send(text, markup); return

    if step_key == 'D1_goals':
        text, markup = multiselect_screen(
            ch, 'D1_goals', 'Какую задачу хотите решить маркетингом? (мультивыбор)',
            D1_GOALS, single=False, add_other_text="📝 Свой вариант", add_preset=True
        )
        _send(text, markup); return

    if step_key == 'D2_channels':
        text, markup = multiselect_screen(
            ch, 'D2_channels', 'Какие каналы продвижения хотите использовать? (мультивыбор)',
            D2_CHANNELS, single=False
        )
        _send(text, markup); return

    if step_key == 'D3_current':
        text, markup = multiselect_screen(
            ch, 'D3_current', 'Есть ли у вас уже действующие кампании или сайт?',
            D3_CURRENT, single=True
        )
        _send(text, markup); return

    if step_key == 'D4_budget':
        text, markup = multiselect_screen(
            ch, 'D4_budget', 'Какой примерный бюджет на маркетинг ежемесячно?',
            D4_BUDGET, single=True
        )
        _send(text, markup); return

    if step_key == 'design':
        text, markup = multiselect_screen(
            ch, 'design', 'Дизайн: уникальный / шаблон / посоветуйте (один вариант)',
            DESIGN, single=True
        )
        _send(text, markup); return

    if step_key == 'content':
        text, markup = multiselect_screen(
            ch, 'content', 'Контент: кто предоставляет материалы? (один вариант)',
            CONTENT, single=True
        )
        _send(text, markup); return

    if step_key == 'integrations_common':
        text, markup = multiselect_screen(
            ch, 'integrations_common', 'Нужны ли Вам интеграции с внешними сервисами?',
            INTEGR_COMMON, single=False
        )
        _send(text, markup); return

    if step_key == 'timeline':
        sol = USER[ch]["solution"]
        opts = []
        if sol in ("Лендинг", "Чат-бот", "Маркетинг (SEO/контекст)"):
            opts = [("1-2w", "1–2 недели"), ("2-4w", "2–4 недели")]
        elif sol == "Корпоративный сайт":
            opts = [("2-4w", "2–4 недели"), ("1-2m", "1–2 месяца")]
        elif sol == "Интернет-магазин":
            opts = [("1-2m", "1–2 месяца"), ("2-4m", "2–4 месяца")]
        text, markup = multiselect_screen(
            ch, 'timeline', 'Как быстро нужно выполнить работу?',
            opts, single=True
        )
        _send(text, markup); return

    if step_key == 'contacts':
        bot.set_state(ch, St.contacts, ch)
        hdr = framed(
            "<b>Благодарю Вас за ответы.</b>\n"
            "<b>Оставьте контактные данные:</b>"
        )
        _send(
            f"{render_progress(done, total)}{hdr}\n"
            "• 📧 Почта\n"
            "• 📱 Телефон\n"
            "• 💬 @username\n\n"
            "<i>Можно ввести любой один вариант текстом.</i>",
            kb(add_back=True, add_home=True)
        )
        return

    if step_key == 'confirm':
        d = USER[ch]["data"]
        name = d.get("name", "—")
        s = [
            f"<b>Имя:</b> {name}",
            f"<b>Организация:</b> {d.get('org_name', '—')} ({d.get('org_category', '—')})",
            f"<b>Есть сайт:</b> {d.get('has_site', '—')}",
        ]
        if d.get("has_site_comment"):
            s.append(f"<b>Комментарий к сайту:</b> {d.get('has_site_comment')}")
        s += [
            f"<b>Продукт/услуга:</b> {d.get('product', '—')}",
            f"<b>Бизнес-задача:</b> {d.get('biz_goal', '—')}",
            f"<b>ЦА:</b> {d.get('audience', '—')}",
            f"<b>Целевое действие:</b> {d.get('user_action', '—')}",
            f"<b>Тип решения:</b> {USER[ch]['solution']}",
            f"<b>Сроки:</b> {pretty_items(d.get('timeline'))}",
            f"<b>Контакты:</b> {d.get('contacts', '—')}",
        ]
        _send(
            f"{render_progress(done, total)}{framed('<b>Проверьте данные</b>')}\n" + "\n".join(s),
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
HTML_KP = r"""
<!doctype html><html><head><meta charset="utf-8">
<title>Коммерческое предложение</title>
<style>
body{font-family:Arial, sans-serif; margin:40px; color:#222; line-height:1.6}
.header{text-align:center;margin-bottom:24px;border-bottom:2px solid {{ brand }};padding-bottom:10px}
.header h1{margin:6px 0 0 0;color:{{ brand }}}
.section{margin:18px 0}
.title{font-weight:bold;font-size:18px;color:{{ brand }};border-bottom:1px solid {{ brand }};padding-bottom:6px;margin-bottom:8px}
.item{margin:6px 0}
.muted{color:{{ muted }}}
.page-break{page-break-before:always}
.note{background:#fff9db;border-left:4px solid #ffd43b;padding:12px;border-radius:6px}
</style></head><body>

<div class="header"><div class="muted">Дата: {{ date }}</div><h1>Коммерческое предложение</h1></div>

<div class="section">
  <div class="title">Данные клиента и цели</div>
  <div class="item"><b>Имя:</b> {{ d.name }}</div>
  <div class="item"><b>Организация:</b> {{ d.org_name }}</div>
  <div class="item"><b>Категория:</b> {{ d.org_category }}</div>
  <div class="item"><b>Есть сайт:</b> {{ d.has_site }}</div>
  {% if d.has_site_comment %}<div class="item"><b>Комментарий к сайту:</b> {{ d.has_site_comment }}</div>{% endif %}
  <div class="item"><b>Продукт/услуга:</b> {{ d.product }}</div>
  <div class="item"><b>Бизнес-задача:</b> {{ d.biz_goal }}</div>
  <div class="item"><b>Целевая аудитория:</b> {{ d.audience }}</div>
  <div class="item"><b>Целевое действие:</b> {{ d.user_action }}</div>
  <div class="item"><b>Тип решения:</b> {{ solution }}</div>
</div>

<div class="page-break"></div>
<div class="section">
  <div class="title">Детализация требований</div>
  {% for k,v in branch.items() %}
    <div class="item"><b>{{ k }}:</b> {{ v }}</div>
  {% endfor %}
</div>

<div class="page-break"></div>
<div class="section">
  <div class="title">Сроки и интеграции</div>
  <div class="item"><b>Дизайн:</b> {{ common.design }}</div>
  <div class="item"><b>Контент:</b> {{ common.content }}</div>
  <div class="item"><b>Интеграции:</b> {{ common.integr }}</div>
  <div class="item"><b>Сроки:</b> {{ common.timeline }}</div>
  <div class="note">Расчёт стоимости и доп. опции будут добавлены позже.</div>
</div>

<div class="page-break"></div>
<div class="section">
  <div class="title">Контакты</div>
  <div class="item"><b>Контакты клиента:</b> {{ d.contacts }}</div>
  <div class="item"><b>Исполнитель:</b> {{ vendor_name }}</div>
  {% if vendor_contacts %}<div class="item"><b>Связь:</b> {{ vendor_contacts }}</div>{% endif %}
</div>
</body></html>
"""


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


def make_pdf(ch: int):
    d = USER[ch]["data"]
    solution = USER[ch]["solution"]
    branch = render_branch_for_pdf(d, solution)
    common = types.SimpleNamespace(
        design=pretty_items(d.get('design')),
        content=pretty_items(d.get('content')),
        integr=pretty_items(d.get('integrations_common')),
        timeline=pretty_items(d.get('timeline')),
    )
    html = Template(HTML_KP).render(
        brand=THEME['brand'], muted=THEME['muted'],
        date=datetime.now().strftime("%d.%m.%Y"),
        d=types.SimpleNamespace(**{k: v if not isinstance(v, dict) else v for k, v in d.items()}),
        solution=solution, branch=branch, common=common,
        vendor_name=os.getenv("VENDOR_NAME", "Ваша студия"),
        vendor_contacts=os.getenv("VENDOR_CONTACTS", "")
    )
    out = f"KP_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    config = pdfkit.configuration(wkhtmltopdf=WKHTML)
    pdfkit.from_string(html, out, configuration=config)
    return out


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
    USER[ch]["flow"] = BASE_FLOW + BRANCH_FLOW[b] + COMMON_FLOW
    USER[ch]["idx"] = USER[ch]["flow"].index('solution')


# =========================
# CALLBACK-и
# =========================
@bot.callback_query_handler(func=lambda c: True)
def on_cb(c: types.CallbackQuery):
    ch, mid, data = c.message.chat.id, c.message.message_id, c.data
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
            safe_edit_text(ch, mid, "🤖 Бриф с ветвлениями после выбора типа сайта. В конце — PDF (без стоимости).",
                           main_menu_kb())
            return
        if data == "ui_home":
            safe_edit_text(ch, mid, "Главное меню:", main_menu_kb())
            return
        if data == "ui_back":
            USER[ch]["idx"] = max(0, USER[ch]["idx"] - 1)
            send_step(ch, cur_step(ch), mid, edit=True)
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
            USER[ch]["data"]["has_site"] = "Да" if data == "yn_yes" else "Нет"
            if data == "yn_yes":
                bot.set_state(ch, St.has_site_comment, ch)
                prompt = framed(
                    "<b>Что вам нравится в вашем сайте, и что бы вы хотели изменить?</b>\n"
                    "<i>Например: «нравится дизайн, но нет корзины».</i>"
                )
                safe_edit_text(
                    ch, mid,
                    f"{render_progress(USER[ch]['idx'] + 1, total_steps(ch))}{prompt}",
                    kb([types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back")],
                       [types.InlineKeyboardButton(f"{EMOJI['home']} В меню", callback_data="ui_home")]))
            else:
                next_step(ch)
                send_step(ch, cur_step(ch), mid, edit=True)
            return

        # goal buttons
        if data.startswith("goal_"):
            mm = {"goal_sell": "Продавать товары или услуги", "goal_leads": "Собирать заявки",
                  "goal_info": "Информировать о деятельности, товарах или услугах",
                  "goal_brand": "Повышать узнаваемость бренда"}
            if data == "goal_custom":
                bot.set_state(ch, St.biz_goal, ch)
                safe_edit_text(
                    ch, mid,
                    f"{render_progress(USER[ch]['idx'] + 1, total_steps(ch))}"
                    f"{framed('Опишите вашу ключевую задачу текстом:')}",
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
                    f"{render_progress(USER[ch]['idx'] + 1, total_steps(ch))}"
                    f"{framed('Укажите нужное действие текстом:')}",
                    kb(add_back=True, add_home=True)
                )
            else:
                USER[ch]["data"]["user_action"] = mm[data]
                next_step(ch)
                send_step(ch, cur_step(ch), mid, edit=True)
            return

        # solution + info
        if data == "sol_info":
            safe_edit_text(ch, mid, SERVICES_INFO,
                           kb([types.InlineKeyboardButton("⬅️ Назад", callback_data="back_solution")], add_home=True))
            return
        if data == "back_solution":
            send_step(ch, 'solution', mid, edit=True)
            return
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
                f"{render_progress(USER[ch]['idx'] + 1, total_steps(ch))}"
                f"{framed('Напишите ваш вариант текстом:')}",
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
        if data == "go_pdf":
            safe_edit_text(ch, mid, "⏳ Генерирую PDF…")
            try:
                path = make_pdf(ch)
                with open(path, "rb") as f:
                    bot.send_document(ch, f, caption="✅ КП готово (черновик без стоимости).")
            except Exception:
                log.exception("pdf error")
                bot.send_message(ch, "⚠️ Ошибка при генерации PDF. Проверьте wkhtmltopdf.")
            return

    except Exception:
        log.exception("callback error")


# =========================
# ТЕКСТОВЫЕ ВВОДЫ
# =========================
@bot.message_handler(commands=['start'])
def on_start(m):
    init_user(m.chat.id)
    # ⚠️ Если фото по пути отсутствует — закомментируйте блок ниже
    try:
        with open("C:/Users/Maksim/Documents/Платон/chat bot/бот КП/фото.jpg", "rb") as photo:
            bot.send_photo(m.chat.id, photo)
    except Exception:
        pass

    bot.send_message(
        m.chat.id,
        "👋 <b>Здравствуйте!  Меня зовут Ева!</b>\n\nЯ помогу Вам создать сайт или настроить продвижение!\n\n"
        "Давайте начнем с нескольких вопросов.",
        reply_markup=main_menu_kb()
    )


@bot.message_handler(state=St.name)
def in_name(m):
    ch = m.chat.id
    t = m.text.strip()
    if len(t) < 2:
        bot.send_message(ch, "❌ Введите имя ещё раз.")
        return
    USER[ch]["data"]["name"] = t
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.org_name)
def in_org_name(m):
    ch = m.chat.id
    t = m.text.strip()
    if len(t) < 2:
        bot.send_message(ch, "❌ Введите название организации.")
        return
    USER[ch]["data"]["org_name"] = t
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.has_site_comment)
def in_site_comment(m):
    ch = m.chat.id
    USER[ch]["data"]["has_site_comment"] = m.text.strip()
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.product)
def in_product(m):
    ch = m.chat.id
    USER[ch]["data"]["product"] = m.text.strip()
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.biz_goal)
def in_goal(m):
    ch = m.chat.id
    USER[ch]["data"]["biz_goal"] = m.text.strip()
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.audience)
def in_aud(m):
    ch = m.chat.id
    USER[ch]["data"]["audience"] = m.text.strip()
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.user_action)
def in_act(m):
    ch = m.chat.id
    USER[ch]["data"]["user_action"] = m.text.strip()
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(state=St.other_input)
def in_other(m):
    ch = m.chat.id
    set_other_value(ch, m.text.strip())
    step = USER[ch]["multiselect_ctx"]["step"]
    send_step(ch, step)


@bot.message_handler(state=St.contacts)
def in_contacts(m):
    ch, txt = m.chat.id, m.text.strip()
    email_re = r'^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$'
    phone_re = r'^\+?\d[\d\-\s]{6,}$'
    if not (txt.startswith("@") or re.match(email_re, txt) or re.match(phone_re, txt)):
        bot.send_message(ch, "❌ Введите корректные контакты (email/телефон/@username).")
        return
    USER[ch]["data"]["contacts"] = txt
    next_step(ch)
    send_step(ch, cur_step(ch))


@bot.message_handler(func=lambda m: True)
def fallback(m):
    ch = m.chat.id
    if ch not in USER:
        on_start(m)
    else:
        send_step(ch, cur_step(ch))


# =========================
# RUN
# =========================
if __name__ == "__main__":
    print("Bot is running…")
    bot.add_custom_filter(telebot.custom_filters.StateFilter(bot))
    bot.infinity_polling()
