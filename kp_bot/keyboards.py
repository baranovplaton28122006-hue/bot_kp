"""
keyboards.py

Конструкторы inline-клавиатур для разных шагов (да/нет, мультивыбор, пагинация, «Назад», «Домой» и т.д.).
(Файл аннотирован автоматически; логика не изменена.)
"""


from telebot import types
from .config import EMOJI, PAGE_SIZE
from .flows import USER
from .utils import framed

# [auto]: функция kb()
def kb(*rows, add_back=False, add_home=False):
    m = types.InlineKeyboardMarkup()
    for row in rows:
        m.row(*row)
    if add_back:
        m.row(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back"))
    return m

# [auto]: функция main_menu_kb()
def main_menu_kb():
    return kb(
        [types.InlineKeyboardButton(f"{EMOJI['start']} Начать", callback_data="act_start")],
        [types.InlineKeyboardButton(f"{EMOJI['about']} О боте", callback_data="act_about")]
    )

# [auto]: функция yn_kb_all_horizontal()
def yn_kb_all_horizontal():
    back = types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back")
    no   = types.InlineKeyboardButton(f"{EMOJI['no']} Нет", callback_data="yn_no")
    yes  = types.InlineKeyboardButton(f"{EMOJI['ok']} Да", callback_data="yn_yes")
    m = types.InlineKeyboardMarkup()
    m.row(back, no, yes)
    return m

# [auto]: функция selected_marker()
def selected_marker(ch: int, key: str) -> str:
    from .config import EMOJI
    ctx = USER[ch].get("multiselect_ctx", {})
    return EMOJI['check'] if key in (ctx.get("selected") or set()) else EMOJI['empty']

# [auto]: функция bottom_row_for_step()
def bottom_row_for_step(step: str, add_back=True, add_other=False, add_done=False):
    row = []
    if add_back:
        row.append(types.InlineKeyboardButton(f"{EMOJI['back']} Назад", callback_data="ui_back"))
    if add_other:
        row.append(types.InlineKeyboardButton("📝 Свой вариант", callback_data=f"other::{step}"))
    if add_done:
        row.append(types.InlineKeyboardButton("✅ Готово", callback_data=f"done::{step}"))
    return row

# [auto]: функция build_paginated_rows()
def build_paginated_rows(ch: int, step: str, options, page: int,
                         add_other_text: str = None, add_preset: bool = False):
    rows = []
    start = page * PAGE_SIZE
    end = min(len(options), start + PAGE_SIZE)

    for key, label in options[start:end]:
        btn = types.InlineKeyboardButton(
            f"{selected_marker(ch, key)} {label}",
            callback_data=f"opt::{step}::{key}"
        )
        rows.append([btn])

    if page > 0:
        rows.append([types.InlineKeyboardButton("◀️ Предыдущие варианты", callback_data=f"page::{step}::{page-1}")])
    if end < len(options):
        rows.append([types.InlineKeyboardButton("Еще варианты ▶️", callback_data=f"page::{step}::{page+1}")])

    if add_preset:
        rows.append([types.InlineKeyboardButton("Предложите стандартный набор", callback_data=f"preset::{step}")])

    if add_other_text:
        other_btn = types.InlineKeyboardButton(add_other_text, callback_data=f"other::{step}")
        done_btn  = types.InlineKeyboardButton("Готово", callback_data=f"done::{step}")
        rows.append([other_btn, done_btn])
    else:
        rows.append([types.InlineKeyboardButton("Готово", callback_data=f"done::{step}")])

    return rows