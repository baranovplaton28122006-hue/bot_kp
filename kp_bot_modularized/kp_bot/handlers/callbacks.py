
"""Callback-обработчики и текстовые хендлеры. Подключается из main.register_callbacks()."""
from telebot import types
from kp_bot.states import St
from kp_bot.ui import main_menu_kb, framed, kb
from kp_bot.services.pdf import make_pdf
from kp_bot.services.multiselect import multiselect_state, toggle_select, save_multiselect, set_other_value, build_paginated_rows
from kp_bot.utils import safe_edit_text, send_temp, safe_delete
from kp_bot.progress import BASE_ORDER, COMMON_ORDER, BRANCH_FLOW
from kp_bot.handlers.send_step import send_step

# ===== Вспомогательные функции сессии =====
# [auto]: функция init_user()
def init_user(USER, ch: int):
    USER[ch] = {
        "idx": 0,
        "flow": BASE_ORDER.copy(),
        "data": {},
        "branch": None,
        "solution": None,
        "multiselect_ctx": {},
        "last_mid": None
    }

# [auto]: функция set_last_mid()
def set_last_mid(USER, ch: int, mid: int | None):
    if ch in USER:
        USER[ch]["last_mid"] = mid

# [auto]: функция cur_step()
def cur_step(USER, ch: int) -> str:
    return USER[ch]['flow'][USER[ch]['idx']]

# [auto]: функция next_step()
def next_step(USER, ch: int):
    USER[ch]['idx'] = min(USER[ch]['idx'] + 1, len(USER[ch]['flow']) - 1)

# [auto]: функция set_step()
def set_step(USER, ch: int, key: str):
    USER[ch]['idx'] = USER[ch]['flow'].index(key)

# [auto]: функция clear_state()
def clear_state(bot, ch: int):
    try:
        bot.delete_state(ch)
    except Exception:
        pass

# [auto]: функция apply_branch_flow()
def apply_branch_flow(USER, ch: int, solution_label: str):
    """Формирует маршрут согласно выбранной ветке и сбрасывает контекст мультивыбора."""
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

    flow = USER[ch]["flow"]
    if "solution" in flow:
        prefix = flow[:flow.index("solution") + 1]
    else:
        prefix = flow[:]
    USER[ch]["flow"] = prefix + BRANCH_FLOW[b] + COMMON_ORDER
    USER[ch]["idx"] = USER[ch]["flow"].index("solution")

# [auto]: функция go_back()
def go_back(bot, USER, ch: int, mid: int | None):
    """Универсальная кнопка «Назад»: учитывает текстовые состояния и мультиввод."""
    try:
        st = bot.get_state(ch, ch)
    except Exception:
        st = None
    st = (st or "").lower()

    if st.endswith(":other_input"):
        step = multiselect_state(USER[ch]).get("step") or cur_step(USER, ch)
        clear_state(bot, ch)
        send_step(bot, USER, ch, step, mid=mid, edit=True)
        return

    if st.endswith(":biz_goal"):
        clear_state(bot, ch)
        send_step(bot, USER, ch, "biz_goal", mid=mid, edit=True)
        return

    if st.endswith(":user_action"):
        clear_state(bot, ch)
        send_step(bot, USER, ch, "user_action", mid=mid, edit=True)
        return

    clear_state(bot, ch)
    USER[ch]["idx"] = max(0, USER[ch]["idx"] - 1)
    send_step(bot, USER, ch, cur_step(USER, ch), mid=mid, edit=True)

# ===== Регистрация обработчиков =====
# [auto]: обработчик register_callbacks()
def register_callbacks(bot, USER, log):
    # /start и /help
    @bot.message_handler(commands=['start', 'help'])
    # [auto]: обработчик on_start()
    def on_start(m):
        ch = m.chat.id
        if ch not in USER:
            init_user(USER, ch)

        # Картинка приветствия (если указана)
        try:
            from kp_bot.config import WELCOME_PHOTO_PATH
            if WELCOME_PHOTO_PATH:
                with open(WELCOME_PHOTO_PATH, "rb") as ph:
                    bot.send_photo(ch, ph)
        except Exception:
            pass

        greet = (
            "👋 <b>Здравствуйте! Меня зовут Ева!</b>\n\n"
            "Я помогу Вам создать сайт\n"
            "или настроить продвижение!\n\n"
            "Давайте начнём с нескольких вопросов."
        )
        bot.send_message(ch, greet, reply_markup=main_menu_kb(), parse_mode="HTML")

    # ===== Текстовые вводы по состояниям =====
    @bot.message_handler(state=St.name, content_types=['text'])
    # [auto]: функция in_name()
    def in_name(m):
        ch = m.chat.id
        USER[ch]["data"]["name"] = m.text.strip()
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    @bot.message_handler(state=St.org_name, content_types=['text'])
    # [auto]: функция in_org_name()
    def in_org_name(m):
        ch = m.chat.id
        USER[ch]["data"]["org_name"] = m.text.strip()
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    @bot.message_handler(state=St.has_site_comment, content_types=['text'])
    # [auto]: функция in_has_site_comment()
    def in_has_site_comment(m):
        ch = m.chat.id
        USER[ch]["data"]["has_site_comment"] = m.text.strip()
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    @bot.message_handler(state=St.product, content_types=['text'])
    # [auto]: функция in_product()
    def in_product(m):
        ch = m.chat.id
        USER[ch]["data"]["product"] = m.text.strip()
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    @bot.message_handler(state=St.biz_goal, content_types=['text'])
    # [auto]: функция in_biz_goal()
    def in_biz_goal(m):
        ch = m.chat.id
        USER[ch]["data"]["biz_goal"] = m.text.strip()
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    @bot.message_handler(state=St.user_action, content_types=['text'])
    # [auto]: функция in_user_action()
    def in_user_action(m):
        ch = m.chat.id
        USER[ch]["data"]["user_action"] = m.text.strip()
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    @bot.message_handler(state=St.other_input, content_types=['text'])
    # [auto]: функция in_other_input()
    def in_other_input(m):
        ch = m.chat.id
        set_other_value(USER[ch], m.text.strip())
        clear_state(bot, ch)
        step = multiselect_state(USER[ch]).get("step") or cur_step(USER, ch)
        send_step(bot, USER, ch, step)

    @bot.message_handler(state=St.contacts, content_types=['text'])
    # [auto]: функция in_contacts_text()
    def in_contacts_text(m):
        ch = m.chat.id
        from kp_bot.utils import parse_contacts, format_contacts
        parsed = parse_contacts(m.text, tg_username=m.from_user.username)
        USER[ch]["data"]["contacts"] = format_contacts(parsed)
        clear_state(bot, ch)
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    # Поделиться контактом кнопкой
    @bot.message_handler(content_types=['contact'], state=St.contacts)
    # [auto]: функция in_contact_obj()
    def in_contact_obj(m):
        ch = m.chat.id
        from kp_bot.utils import parse_contacts, format_contacts
        parsed = parse_contacts("", tg_username=m.from_user.username, phone_from_share=(m.contact.phone_number if m.contact else None))
        USER[ch]["data"]["contacts"] = format_contacts(parsed)
        safe_delete(bot, ch, m.message_id)
        send_temp(bot, ch, "✅ Контакт добавлен!", ttl=3, reply_markup=types.ReplyKeyboardRemove())
        next_step(USER, ch)
        send_step(bot, USER, ch, cur_step(USER, ch))

    # ===== Все callback-и =====
    @bot.callback_query_handler(func=lambda c: True)
    # [auto]: обработчик on_cb()
    def on_cb(c):
        ch, mid, data = c.message.chat.id, c.message.message_id, c.data
        if ch not in USER:
            init_user(USER, ch)
        set_last_mid(USER, ch, mid)

        # Навигация
        if data == "ui_back":
            go_back(bot, USER, ch, mid)
            return
        if data == "ui_home":
            safe_edit_text(bot, ch, mid, "Главное меню:", main_menu_kb())
            return

        # Ответим на колбэк, чтобы убрать "часики"
        try:
            bot.answer_callback_query(c.id)
        except Exception:
            pass

        # Старт / О боте
        if data == "act_start":
            init_user(USER, ch)
            send_step(bot, USER, ch, 'name', mid, edit=True)
            return
        if data == "act_about":
            about_text = (
                "ℹ️ <b>О боте</b>\n\n"
                "1) Отвечаете на вопросы (≈3–5 минут).\n"
                "2) Выбираете решение и нужные опции.\n"
                "3) Получаете готовое КП в PDF."
            )
            about_kb = types.InlineKeyboardMarkup()
            about_kb.add(types.InlineKeyboardButton("📝 Начать", callback_data="act_start"))
            safe_edit_text(bot, ch, mid, about_text, about_kb)
            return

        # Категории (пример: org_category через cat_*)
        if data.startswith("cat_"):
            USER[ch]["data"]["org_category"] = {
                "cat_fl": "Физическое лицо",
                "cat_ip": "ИП",
                "cat_ul": "Юридическое лицо",
                "cat_other": "Свой вариант"
            }.get(data, "Свой вариант")
            next_step(USER, ch)
            send_step(bot, USER, ch, cur_step(USER, ch), mid, edit=True)
            return

        # Есть сайт? (yn_* на шаге has_site)
        if data in ("yn_yes", "yn_no") and cur_step(USER, ch) == "has_site":
            USER[ch].setdefault("data", {})["has_site"] = "Да" if data == "yn_yes" else "Нет"
            if data == "yn_yes":
                USER[ch]["flow"] = ["name", "org_name", "has_site", "has_site_comment", "contacts", "confirm"]
                set_step(USER, ch, "has_site_comment")
                bot.set_state(ch, St.has_site_comment, ch)
                prompt = framed("4. <b>Что вам нравится в вашем сайте, и что бы вы хотели изменить?</b>\n<i>Например: «нравится дизайн, но нет корзины».</i>")
                kb_back = types.InlineKeyboardMarkup()
                kb_back.add(types.InlineKeyboardButton("⬅️ Назад", callback_data='ui_back'))
                safe_edit_text(bot, ch, mid, prompt, kb_back)
            else:
                USER[ch]["flow"] = ["name", "org_name", "has_site", "biz_goal", "user_action", "product", "solution"]
                set_step(USER, ch, "biz_goal")
                send_step(bot, USER, ch, "biz_goal", mid, edit=True)
            return

        # Цели
        if data.startswith("goal_"):
            mapping = {
                "goal_sell": "Продавать товары или услуги",
                "goal_leads": "Собирать заявки",
                "goal_info2": "Информировать о товарах или услугах",
                "goal_info": "Информировать о деятельности",
                "goal_brand": "Повышать узнаваемость бренда",
            }
            if data == "goal_custom":
                bot.set_state(ch, St.biz_goal, ch)
                safe_edit_text(bot, ch, mid, "Опишите вашу ключевую задачу текстом:", kb(add_back=True, add_home=True))
            else:
                USER[ch]["data"]["biz_goal"] = mapping.get(data, "")
                next_step(USER, ch)
                send_step(bot, USER, ch, cur_step(USER, ch), mid, edit=True)
            return

        # Целевое действие
        if data.startswith("act_"):
            mapping = {
                "act_buy": "Купить",
                "act_call": "Позвонить",
                "act_lead": "Оставить заявку",
                "act_sub": "Подписаться"
            }
            if data == "act_custom":
                bot.set_state(ch, St.user_action, ch)
                safe_edit_text(bot, ch, mid, "Укажите нужное действие текстом:", kb(add_back=True, add_home=True))
            else:
                USER[ch]["data"]["user_action"] = mapping.get(data, "")
                next_step(USER, ch)
                send_step(bot, USER, ch, cur_step(USER, ch), mid, edit=True)
            return

        # Выбор решения
        if data.startswith("sol_"):
            label = {
                "sol_land": "Лендинг",
                "sol_shop": "Интернет-магазин",
                "sol_bot": "Чат-бот",
                "sol_corp": "Корпоративный сайт",
                "sol_mkt": "Маркетинг (SEO/контекст)"
            }.get(data, "Маркетинг (SEO/контекст)")
            apply_branch_flow(USER, ch, label)
            next_step(USER, ch)
            send_step(bot, USER, ch, cur_step(USER, ch), mid, edit=True)
            return

        # Мультивыбор: пагинация/выбор/сохранение/«свой вариант»
        if data.startswith("page::"):
            _, step, page = data.split("::")
            multiselect_state(USER[ch])["page"] = int(page)
            send_step(bot, USER, ch, step, mid, edit=True)
            return

        if data.startswith("opt::"):
            _, step, key = data.split("::")
            toggle_select(USER[ch], key)
            send_step(bot, USER, ch, step, mid, edit=True)
            return

        if data.startswith("done::"):
            _, step = data.split("::")
            save_multiselect(USER[ch])
            next_step(USER, ch)
            send_step(bot, USER, ch, cur_step(USER, ch), mid, edit=True)
            return

        if data.startswith("other::"):
            _, step = data.split("::")
            bot.set_state(ch, St.other_input, ch)
            safe_edit_text(bot, ch, mid, "Введите свой вариант текстом:", kb(add_back=True, add_home=True))
            return

        # Создать КП
        if data == "go_pdf":
            path = make_pdf(USER[ch], out_dir="generated_kp")
            safe_edit_text(bot, ch, mid, f"Готово! Файл сохранён: <code>{path}</code>")
            return