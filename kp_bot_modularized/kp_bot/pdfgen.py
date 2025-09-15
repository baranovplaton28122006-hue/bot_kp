"""
pdfgen.py

Генерация HTML (и далее PDF) коммерческого предложения на основе шаблона Jinja2 и данных анкеты.
(Файл аннотирован автоматически; логика не изменена.)
"""


from jinja2 import Template
from datetime import datetime
import os, re
from .options import LABELS, humanize_dict
from .flows import USER
from .utils import framed
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

BASE_PRICES = {
    "Лендинг": 180000,
    "Корпоративный сайт": 150000,
    "Интернет-магазин": 240000,
    "Чат-бот": 120000,
    "Маркетинг (SEO/контекст)": 0,
}

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

# [auto]: функция pretty_items()
def pretty_items(entry):
    if not entry:
        return "—"
    if isinstance(entry, dict) and "items" in entry:
        items = entry["items"]
        text = ", ".join(items)
        return text + (f"; Другое: {entry.get('other')}" if entry.get("other") else "")
    return str(entry)

# [auto]: функция humanize_list()
def humanize_list(step: str, keys: list[str]) -> list[str]:
    return [LABELS.get(step, {}).get(k, k) for k in (keys or [])]

# [auto]: функция humanize_dict()
def humanize_dict(step: str, dct: dict | None) -> str:
    if not dct:
        return ""
    items = humanize_list(step, dct.get("items", []))
    if dct.get("other"):
        items.append(f"Другое: {dct['other']}")
    return "<br>• " + "<br>• ".join(items) if items else ""

# [auto]: функция build_kp_context()
def build_kp_context(ch: int):
    d = USER[ch]["data"]
    site_type = USER[ch].get("solution", "—")

    parts = []
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

    else:
        for key, title in [("D1_goals","Цели маркетинга"), ("D2_channels","Каналы продвижения")]:
            if d.get(key):
                html_block = humanize_dict(key, d[key])
                if html_block:
                    parts.append(f"<div class='subsection'><div class='subsection-title'>{title}</div>{html_block}</div>")
        selections_title = "Цели и каналы маркетинга"

    selections_text = "".join(parts)

    base_price = BASE_PRICES.get(site_type, 0)
    options = []
    for name, price in OPTION_PRICES.items():
        if name == "Система онлайн-записи" and 'A2_functions' in d and 'booking' in d['A2_functions'].get('items', []):
            options.append({"name": name, "price": price})
        elif name == "Интеграция с соцсетями" and (
            ('A2_functions' in d and 'social' in d['A2_functions'].get('items', [])) or
            ('C3_integrations' in d and 'mess' in d['C3_integrations'].get('items', []))
        ):
            options.append({"name": name, "price": price})
        elif name in ("SEO-базовая оптимизация","Техническая поддержка (1 месяц)","Фирменный стиль","Интеграция эквайринга","Система доставки","Мультивалютность"):
            options.append({"name": name, "price": price})

    total_opts = sum(x["price"] for x in options if isinstance(x["price"], (int,float)))
    total_price = base_price + total_opts
    has_manager_options = any(x["price"] == "manager" for x in options)

    tl_items = (d.get("timeline") or {}).get("items") or [None]
    tl_code = tl_items[0]
    timeline_map = {"1-2w":"1–2 недели","2-4w":"2–4 недели","1-2m":"1–2 месяца","2-4m":"2–4 месяца"}
    tl_label = timeline_map.get(tl_code, "—")
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
            "design": pretty_items(d.get("design")),
            "content": pretty_items(d.get("content")),
            "integr": pretty_items(d.get("C3_integrations")),
            "timeline": tl_label,
        },
        "budget": pretty_items(d.get("D4_budget")),
        "selections_title": selections_title if selections_text else "",
        "selections_text": selections_text,
        "options": options,
        "base_price": base_price,
        "total_price": total_price,
        "dev_time": dev_time or "",
        "has_manager_options": has_manager_options,
    }
    return ctx

# [auto]: функция make_kp_html()
def make_kp_html(ch: int) -> str:
    from glob import glob
    ctx = build_kp_context(ch)
    html_text = Template(KP_TEMPLATE).render(**ctx)
    out_dir = os.path.join(os.getcwd(), "generated_kp")
    os.makedirs(out_dir, exist_ok=True)
    raw_contacts = USER[ch]["data"].get("contacts", "")
    phone = re.sub(r"\D", "", raw_contacts) or "unknown"
    date_str = datetime.now().strftime("%Y%m%d")
    pattern = os.path.join(out_dir, f"KP_{phone}_{date_str}_*.html")
    seq = len(glob(pattern)) + 1
    out_path = os.path.join(out_dir, f"KP_{phone}_{date_str}_{seq}.html")
    while os.path.exists(out_path):
        seq += 1
        out_path = os.path.join(out_dir, f"KP_{phone}_{date_str}_{seq}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return out_path

# [auto]: функция make_pdf()
def make_pdf(ch: int) -> str:
    return make_kp_html(ch)