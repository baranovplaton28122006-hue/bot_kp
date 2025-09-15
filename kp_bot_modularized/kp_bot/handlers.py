"""
handlers.py

Главные обработчики сообщений и callback-кнопок. Управляет навигацией по шагам анкеты и записью данных пользователя.
(Файл аннотирован автоматически; логика не изменена.)
"""


import os
from telebot import types
import kp_bot.runtime as runtime
from .states import St
from .flows import USER, init_user, get_flow, cur_step, set_step, next_step, set_last_mid, get_last_mid, apply_branch_flow, go_back
from .keyboards import kb, main_menu_kb
from .render import send_step
from .utils import safe_edit_text, send_temp, framed, h, safe_delete
from .multiselect import multiselect_state, toggle_select, save_multiselect, set_other_value, start_multiselect
from .options import *
from .pdfgen import make_kp_html
from .contacts import parse_contacts, format_contacts

# [auto]: функция register()
def register(bot_instance):
    # share contact inline button
    @bot_instance.callback_query_handler(func=lambda c: c.data == "share_contact")
    # [auto]: обработчик on_share_contact()
    def on_share_contact(c):
        ch = c.message.chat.id
        bot_instance.answer_callback_query(c.id)
        share_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        share_kb.add(types.KeyboardButton("📱 Отправить мой номер", request_contact=True))
        send_temp(
            ch,
            "👇 Нажмите кнопку «📱 Отправить мой номер» ниже.\n"
            "Я автоматически добавлю ваш номер телефона и Telegram-ник в контакты КП.",
            ttl=6,
            reply_markup=share_kb
        )

    @bot_instance.message_handler(content_types=['contact'], state=St.contacts)
    # [auto]: функция in_contact_obj()
    def in_contact_obj(m):
        ch = m.chat.id
        parsed = parse_contacts("", tg_username=m.from_user.username,
                                phone_from_share=(m.contact.phone_number if m.contact else None))
        USER[ch]["data"]["contacts"] = format_contacts(parsed)
        safe_delete(ch, m.message_id)
        send_temp(ch, "✅ Контакт добавлен!", ttl=3, reply_markup=types.ReplyKeyboardRemove())
        next_step(ch)
        send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.callback_query_handler(func=lambda c: True)
    # [auto]: обработчик on_cb()
    def on_cb(c):
        ch, mid, data = c.message.chat.id, c.message.message_id, c.data
        if ch not in USER:
            init_user(ch)
        set_last_mid(ch, mid)

        if data == "ui_back":
            go_back(ch, mid); return
        try:
            bot_instance.answer_callback_query(c.id)
        except Exception:
            pass
        runtime.log.info(f"cb:{data} idx={USER.get(ch, {}).get('idx')} step={USER.get(ch, {}).get('flow', [None])[USER.get(ch, {}).get('idx', 0)] if USER.get(ch) else '—'}")

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
                about_kb.add(types.InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/PlaBarov"))  # noqa
                safe_edit_text(ch, mid, about_text, about_kb)
                return

            if data == "ui_home":
                safe_edit_text(ch, mid, "Главное меню:", main_menu_kb()); return

            if data.startswith("cat_"):
                USER[ch]["data"]["org_category"] = {
                    "cat_fl": "Физическое лицо", "cat_ip": "ИП", "cat_ul": "Юридическое лицо", "cat_other": "Свой вариант"
                }[data]
                next_step(ch); send_step(ch, cur_step(ch), mid, edit=True); return

            if data in ("yn_yes", "yn_no") and cur_step(ch) == "has_site":
                USER[ch].setdefault("data", {})["has_site"] = "Да" if data == "yn_yes" else "Нет"
                if data == "yn_yes":
                    USER[ch]["flow"] = ["name", "org_name", "has_site", "has_site_comment", "contacts", "confirm"]
                    set_step(ch, "has_site_comment")
                    bot_instance.set_state(ch, St.has_site_comment, ch)
                    send_step(ch, "has_site_comment", mid, edit=True)
                else:
                    USER[ch]["flow"] = ["name", "org_name", "has_site", "biz_goal", "user_action", "product", "solution"]
                    set_step(ch, "biz_goal")
                    send_step(ch, "biz_goal", mid, edit=True)
                return

            if data.startswith("goal_"):
                mm = {"goal_sell": "Продавать товары или услуги", "goal_leads": "Собирать заявки",
                      "goal_info2": "Информировать о товарах или услугах",
                      "goal_info": "Информировать о деятельности",
                      "goal_brand": "Повышать узнаваемость бренда"}
                if data == "goal_custom":
                    bot_instance.set_state(ch, St.biz_goal, ch)
                    safe_edit_text(ch, mid, "Опишите вашу ключевую задачу текстом:", kb())
                else:
                    USER[ch]["data"]["biz_goal"] = mm[data]
                    next_step(ch); send_step(ch, cur_step(ch), mid, edit=True)
                return

            if data.startswith("act_"):
                mm = {"act_buy": "Купить", "act_call": "Позвонить", "act_lead": "Оставить заявку", "act_sub": "Подписаться"}
                if data == "act_custom":
                    bot_instance.set_state(ch, St.user_action, ch)
                    safe_edit_text(ch, mid, "Укажите нужное действие текстом:", kb())
                else:
                    USER[ch]["data"]["user_action"] = mm[data]
                    next_step(ch); send_step(ch, cur_step(ch), mid, edit=True)
                return

            if data.startswith("sol_"):
                label = {"sol_land": "Лендинг", "sol_shop": "Интернет-магазин", "sol_corp": "Корпоративный сайт",
                         "sol_bot": "Чат-бот", "sol_mkt": "Маркетинг (SEO/контекст)"}[data]
                apply_branch_flow(ch, label)
                next_step(ch)
                send_step(ch, cur_step(ch), mid, edit=True)
                return

            if data.startswith("opt::"):
                _, step, key = data.split("::", 2)
                from .multiselect import toggle_select
                toggle_select(ch, key)
                send_step(ch, step, mid, edit=True); return

            if data.startswith("done::"):
                _, step = data.split("::", 1)
                from .multiselect import save_multiselect
                save_multiselect(ch)
                next_step(ch); send_step(ch, cur_step(ch), mid, edit=True); return

            if data.startswith("other::"):
                _, step = data.split("::", 1)
                multiselect_state(ch)["step"] = step
                bot_instance.set_state(ch, St.other_input, ch)
                safe_edit_text(ch, mid, "Напишите ваш вариант текстом:", kb())
                return

            if data.startswith("preset::"):
                _, step = data.split("::", 1)
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
                send_step(ch, step, mid, edit=True); return

            if data.startswith("page::"):
                _, step, page_s = data.split("::", 2)
                st = multiselect_state(ch)
                st["step"] = step
                st["page"] = max(0, int(page_s))
                send_step(ch, step, mid, edit=True); return

            if data in ("go_pdf", "go_kp"):
                try:
                    path = make_kp_html(ch)
                    with open(path, "rb") as f:
                        bot_instance.send_document(
                            ch, f,
                            visible_file_name=os.path.basename(path),
                            caption="✅ Ваше коммерческое предложение готово!"
                        )
                    mgr_kb = types.InlineKeyboardMarkup()
                    mgr_kb.add(types.InlineKeyboardButton("📞 Связаться с менеджером", url="https://t.me/PlaBarov"))
                    bot_instance.send_message(ch, "Если остались вопросы — напишите менеджеру:", reply_markup=mgr_kb)
                except Exception as e:
                    runtime.log.error(f"make_kp_html failed: {e}")
                    bot_instance.send_message(ch, "Не удалось сформировать файл. Сообщите менеджеру, пожалуйста.")
                return
        except Exception:
            runtime.log.exception("callback error")

    # === MESSAGE HANDLERS (text states) ===
    @bot_instance.message_handler(commands=['start'])
    # [auto]: обработчик on_start()
    def on_start(m):
        init_user(m.chat.id)
        try:
            with open("C:/Users/Maksim/Documents/Платон/chat bot/бот КП/фото.jpg", "rb") as photo:
                bot_instance.send_photo(m.chat.id, photo)
        except Exception:
            pass
        msg = bot_instance.send_message(
            m.chat.id,
            "👋 <b>Здравствуйте!  Меня зовут Ева!</b>\n\n"
            "Я помогу Вам создать сайт\n"
            "или настроить продвижение!\n\n"
            "Давайте начнем с нескольких вопросов.",
            reply_markup=main_menu_kb()
        )
        set_last_mid(m.chat.id, msg.message_id)

    @bot_instance.message_handler(state=St.name)
    # [auto]: функция in_name()
    def in_name(m):
        ch = m.chat.id
        name = (m.text or "").strip()
        USER[ch]["data"]["name"] = name
        safe_delete(ch, m.message_id)
        next_step(ch)
        from .utils import h
        safe_edit_text(ch, get_last_mid(ch), f"Рада нашему знакомству, <b>{h(name)}</b>!")
        from threading import Timer
        Timer(2, lambda: send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)).start()

    @bot_instance.message_handler(state=St.org_name)
    # [auto]: функция in_org_name()
    def in_org_name(m):
        ch = m.chat.id
        t = (m.text or "").strip()
        safe_delete(ch, m.message_id)
        if len(t) < 2:
            bot_instance.send_message(ch, "❌ Введите название организации."); return
        USER[ch]["data"]["org_name"] = t
        next_step(ch); send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.has_site_comment)
    # [auto]: функция in_site_comment()
    def in_site_comment(m):
        ch = m.chat.id
        USER[ch]["data"]["has_site_comment"] = (m.text or "").strip()
        safe_delete(ch, m.message_id)
        flow = get_flow(ch)
        extra = []
        if "contacts" not in flow: extra.append("contacts")
        if "confirm" not in flow: extra.append("confirm")
        if extra:
            USER[ch]["flow"] = flow + extra
        USER[ch]["idx"] = USER[ch]["flow"].index("contacts")
        from .flows import clear_state
        clear_state(ch)
        send_step(ch, "contacts", mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.product)
    # [auto]: функция in_product()
    def in_product(m):
        ch = m.chat.id
        USER[ch]["data"]["product"] = (m.text or "").strip()
        safe_delete(ch, m.message_id)
        next_step(ch); send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.biz_goal)
    # [auto]: функция in_goal()
    def in_goal(m):
        ch = m.chat.id
        USER[ch]["data"]["biz_goal"] = (m.text or "").strip()
        safe_delete(ch, m.message_id)
        next_step(ch); send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.audience)
    # [auto]: функция in_aud()
    def in_aud(m):
        ch = m.chat.id
        USER[ch]["data"]["audience"] = (m.text or "").strip()
        safe_delete(ch, m.message_id)
        next_step(ch); send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.user_action)
    # [auto]: функция in_act()
    def in_act(m):
        ch = m.chat.id
        USER[ch]["data"]["user_action"] = (m.text or "").strip()
        safe_delete(ch, m.message_id)
        next_step(ch); send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.other_input)
    # [auto]: функция in_other()
    def in_other(m):
        ch = m.chat.id
        set_other_value(ch, (m.text or "").strip())
        safe_delete(ch, m.message_id)
        step = USER[ch]["multiselect_ctx"]["step"]
        send_step(ch, step, mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(state=St.contacts)
    # [auto]: функция in_contacts()
    def in_contacts(m):
        ch, txt = m.chat.id, (m.text or "").strip()
        parsed = parse_contacts(txt, m.from_user.username)
        safe_delete(ch, m.message_id)
        if not parsed:
            send_temp(ch, "❌ Введите email, телефон (цифрами) или @username.", ttl=6); return
        USER[ch]["data"]["contacts"] = format_contacts(parsed)
        send_temp(ch, "✅ Контакт добавлен!", ttl=5)
        next_step(ch); send_step(ch, cur_step(ch), mid=get_last_mid(ch), edit=True)

    @bot_instance.message_handler(func=lambda m: True)
    # [auto]: функция fallback()
    def fallback(m):
        ch = m.chat.id
        safe_delete(ch, m.message_id)
        if ch not in USER:
            on_start(m)