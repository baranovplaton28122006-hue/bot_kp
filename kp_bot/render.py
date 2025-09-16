"""
render.py

Отрисовка экранов шагов: формирование текста, кнопок и безопасная отправка/редактирование сообщений.
(Файл аннотирован автоматически; логика не изменена.)
"""

from telebot import types
import kp_bot.runtime as runtime
from .states import St
from .utils import safe_edit_text, framed, framed_bottom, send_temp
from .config import EMOJI
from .flows import (
    USER, get_flow, numbered_title, cur_step, set_step, next_step,
    set_last_mid, get_last_mid, render_for_step
)
from .keyboards import kb, main_menu_kb, yn_kb_all_horizontal, build_paginated_rows, bottom_row_for_step
from .multiselect import ensure_multiselect, multiselect_state
from .options import *

# [auto]: функция multiselect_screen()
def multiselect_screen(ch: int, step: str, title_html: str, options,
                       single: bool = False, add_other_text: str = None, add_preset: bool = False):
    ensure_multiselect(ch, step, single=single)
    page = multiselect_state(ch)["page"]
    rows = build_paginated_rows(ch, step, options, page, add_other_text=add_other_text, add_preset=add_preset)

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

    bottom = bottom_row_for_step(step, add_back=True, add_other=(other_btn is not None), add_done=(done_btn is not None))
    if other_btn is not None:
        bottom[1] = other_btn
    if done_btn is not None:
        bottom[-1] = done_btn
    rows.append(bottom)

    m = types.InlineKeyboardMarkup()
    for r in rows:
        if r:
            m.row(*r)

    text = f"{render_for_step(ch, step)}{framed(f'<b>{title_html}</b>')}"
    return text, m


# [auto]: функция send_step()
def send_step(ch: int, step_key: str, mid: int = None, edit: bool = False):
    flow = get_flow(ch)

    # [auto]: функция NT()
    def NT(step: str, text_html: str) -> str:
        return numbered_title(ch, step, text_html)

    # [auto]: функция _send()
    def _send(text, markup=None):
        if edit and mid:
            try:
                safe_edit_text(ch, mid, text, markup)
                set_last_mid(ch, mid)
                return
            except Exception:
                pass
        m = runtime.bot.send_message(ch, text, reply_markup=markup)
        set_last_mid(ch, m.message_id)

    # === BASE ===
    if step_key == 'name':
        runtime.bot.set_state(ch, St.name, ch)
        title = NT('name', '<b>Представьтесь пожалуйста, как Вас зовут?</b>')
        _send(f"{render_for_step(ch, 'name')}{framed(title)}\n")
        return

    if step_key == 'org_name':
        runtime.bot.set_state(ch, St.org_name, ch)
        title = NT('org_name', '<b>Как называется ваша организация?</b>')
        _send(f"{render_for_step(ch, 'org_name')}{framed(title)}", kb(add_back=True, add_home=True))
        return

    if step_key == 'org_category':
        runtime.bot.set_state(ch, St.org_category, ch)
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
        runtime.bot.set_state(ch, St.has_site, ch)
        title = NT('has_site', '<b>У вас уже есть сайт?</b>')
        _send(f"{render_for_step(ch, 'has_site')}{framed(title)}", yn_kb_all_horizontal())
        return

    # >>> ВАЖНО: этот блок был вставлен снаружи функции. Теперь он внутри send_step <<<
    if step_key == 'has_site_comment':
        runtime.bot.set_state(ch, St.has_site_comment, ch)
        title = NT('has_site_comment', '<b>Что вам нравится в вашем сайте, и что бы вы хотели изменить?</b>')
        _send(
            f"{render_for_step(ch, 'has_site_comment')}{framed(title)}\n"
            "<i>Например: «нравится дизайн, но нет корзины».</i>",
            kb(add_back=True, add_home=True)
        )
        return

    if step_key == 'product':
        runtime.bot.set_state(ch, St.product, ch)
        title = NT('product', '<b>Какой продукт или услугу Вы планируете продвигать?</b>')
        _send(f"{render_for_step(ch, 'product')}{framed(title)}", kb(add_back=True, add_home=True))
        return

    if step_key == 'biz_goal':
        title = NT('biz_goal', '<b>Какую главную задачу должен решить сайт?</b>')
        _send(
            f"{render_for_step(ch, 'biz_goal')}{framed(title)}",
            kb(
                [types.InlineKeyboardButton("Информировать о товарах, услугах", callback_data="goal_info2")],
                [types.InlineKeyboardButton("Информировать о деятельности", callback_data="goal_info")],
                [types.InlineKeyboardButton("Повышать узнаваемость бренда", callback_data="goal_brand")],
                [types.InlineKeyboardButton("Продавать товары или услуги", callback_data="goal_sell")],
                [types.InlineKeyboardButton("Собирать заявки", callback_data="goal_leads")],
                add_back=True
            )
        )
        return

    if step_key == 'audience':
        runtime.bot.set_state(ch, St.audience, ch)
        title = NT('audience', '<b>Кто Ваши потенциальные клиенты?</b>')
        _send(
            f"{render_for_step(ch, 'audience')}{framed_bottom(title)}\n"
            "Напишите пол, возраст, род деятельности или интересы.\n\n"
            "<i>Например: «женщины; 25–40 лет; интересующиеся модой».</i>\n",
            kb(add_back=True)
        )
        return

    if step_key == 'user_action':
        title = NT('user_action', '<b>Какое целевое действие должен совершить пользователь на сайте?</b>')
        _send(
            f"{render_for_step(ch, 'user_action')}{framed(title)}",
            kb(
                [types.InlineKeyboardButton("Оставить заявку", callback_data="act_lead")],
                [types.InlineKeyboardButton("Подписаться", callback_data="act_sub")],
                [types.InlineKeyboardButton("Позвонить", callback_data="act_call")],
                [types.InlineKeyboardButton("Купить", callback_data="act_buy")],
                add_back=True
            )
        )
        return

    if step_key == 'solution':
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

    # === BRANCH & COMMON ===
    if step_key == 'A1_blocks':
        t_html = NT('A1_blocks', '<b>Выберите ключевые блоки/разделы:</b>')
        sol = USER[ch]["solution"]
        opts = A1_LANDING if sol == "Лендинг" else A1_CORP
        text, markup = multiselect_screen(ch, 'A1_blocks', t_html, opts, single=False, add_other_text="📝 Свой вариант", add_preset=True)
        _send(text, markup); return

    if step_key == 'A2_functions':
        t_html = NT('A2_functions', '<b>Планируете ли Вы функционал на сайте?</b>')
        text, markup = multiselect_screen(ch, 'A2_functions', t_html, A2_FUNCTIONS, single=False, add_other_text="📝 Свой вариант")
        _send(text, markup); return

    if step_key == 'B1_sections':
        t_html = NT('B1_sections', '<b>Разделы интернет-магазина:</b>')
        text, markup = multiselect_screen(ch, 'B1_sections', t_html, B1_SECTIONS, single=False, add_other_text="📝 Свой вариант", add_preset=True)
        _send(text, markup); return

    if step_key == 'B2_assort':
        t_html = NT('B2_assort', '<b>Сколько примерно товаров планируете?</b>')
        text, markup = multiselect_screen(ch, 'B2_assort', t_html, B2_ASSORT, single=True)
        _send(text, markup); return

    if step_key == 'B3_functions':
        t_html = NT('B3_functions', '<b>Какой функционал нужен в магазине, кроме корзины?</b>')
        text, markup = multiselect_screen(ch, 'B3_functions', t_html, B3_FUNCTIONS, single=False)
        _send(text, markup); return

    if step_key == 'C1_tasks':
        t_html = NT('C1_tasks', '<b>Где чат-бот принесёт максимальную пользу?</b>')
        text, markup = multiselect_screen(ch, 'C1_tasks', t_html, C1_TASKS, single=False, add_other_text="📝 Свой вариант", add_preset=True)
        _send(text, markup); return

    if step_key == 'C2_platforms':
        t_html = NT('C2_platforms', '<b>В каких мессенджерах/платформах должен работать чат-бот?</b>')
        text, markup = multiselect_screen(ch, 'C2_platforms', t_html, C2_PLATFORMS, single=False, add_other_text="📝 Свой вариант")
        _send(text, markup); return

    if step_key == 'C3_integrations':
        t_html = NT('C3_integrations', '<b>Нужны ли Вам интеграции с внешними сервисами?</b>')
        text, markup = multiselect_screen(ch, 'C3_integrations', t_html, C3_INTEGR, single=False)
        _send(text, markup); return

    if step_key == 'D1_goals':
        t_html = NT('D1_goals', '<b>Какую задачу хотите решить маркетингом?</b>')
        text, markup = multiselect_screen(ch, 'D1_goals', t_html, D1_GOALS, single=False, add_other_text="📝 Свой вариант", add_preset=True)
        _send(text, markup); return

    if step_key == 'D2_channels':
        t_html = NT('D2_channels', '<b>Какие каналы продвижения хотите использовать?</b>')
        text, markup = multiselect_screen(ch, 'D2_channels', t_html, D2_CHANNELS, single=False)
        _send(text, markup); return

    if step_key == 'D4_budget':
        t_html = NT('D4_budget', '<b>Какой примерный бюджет на маркетинг планируете ежемесячно?</b>')
        text, markup = multiselect_screen(ch, 'D4_budget', t_html, D4_BUDGET, single=True)
        _send(text, markup); return

    if step_key == 'design':
        t_html = NT('design', '<b>Какой дизайн Вы хотите?</b>')
        text, markup = multiselect_screen(ch, 'design', t_html, DESIGN, single=True)
        _send(text, markup); return

    if step_key == 'content':
        t_html = NT('content', '<b>Кто предоставляет контент материалы?</b>')
        text, markup = multiselect_screen(ch, 'content', t_html, CONTENT, single=True)
        _send(text, markup); return

    if step_key == 'timeline':
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
        runtime.bot.set_state(ch, St.contacts, ch)
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
            kb([types.InlineKeyboardButton("📱 Поделиться контактом", callback_data="share_contact")], add_back=True, add_home=True)
        )
        return

    if step_key == 'confirm':
        d = USER[ch]["data"]
        tl_items = (d.get("timeline") or {}).get("items") or []
        tl_code = tl_items[0] if tl_items else None
        from .options import LABELS, humanize_list
        tl_label = LABELS["timeline"].get(tl_code, "—")
        design_text = ", ".join(humanize_list("design", (d.get("design") or {}).get("items", []))) or "—"
        content_text = ", ".join(humanize_list("content", (d.get("content") or {}).get("items", []))) or "—"
        budget_items = (d.get("D4_budget") or {}).get("items") or []
        budget_code = budget_items[0] if budget_items else None
        budget_text = LABELS["D4_budget"].get(budget_code, "—")

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
            kb([types.InlineKeyboardButton(f"{EMOJI['confirm']} Создать КП", callback_data="go_pdf")], add_home=True)
        )
        return