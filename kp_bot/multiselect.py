"""
multiselect.py

Модуль проекта Telegram-бота для брифа/КП.
(Файл аннотирован автоматически; логика не изменена.)
"""


from typing import List
from .flows import USER
# [auto]: функция multiselect_state()
def multiselect_state(ch: int):
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

# [auto]: функция start_multiselect()
def start_multiselect(ch: int, step: str, single: bool = False, preset: List[str] = None, seed: List[str] = None):
    ctx = multiselect_state(ch)
    ctx["step"] = step
    ctx["single"] = single
    ctx["preset"] = preset or []
    ctx["selected"] = set(seed or [])
    ctx["page"] = 0

# [auto]: функция ensure_multiselect()
def ensure_multiselect(ch: int, step: str, single: bool = False):
    ctx = multiselect_state(ch)
    if ctx["step"] != step:
        prev_items = USER[ch]["data"].get(step, {}).get("items", [])
        start_multiselect(ch, step, single=single, seed=prev_items)
    else:
        ctx["single"] = single

# [auto]: функция toggle_select()
def toggle_select(ch: int, key: str):
    ctx = multiselect_state(ch)
    if ctx["single"]:
        ctx["selected"] = set([key])
    else:
        if key in ctx["selected"]:
            ctx["selected"].remove(key)
        else:
            ctx["selected"].add(key)

# [auto]: функция set_other_value()
def set_other_value(ch: int, text: str):
    d = USER[ch]["data"]
    step = multiselect_state(ch)["step"]
    d.setdefault(step, {"items": [], "other": None})
    d[step]["other"] = text

# [auto]: функция save_multiselect()
def save_multiselect(ch: int):
    ctx = multiselect_state(ch)
    d = USER[ch]["data"]
    d[ctx["step"]] = {"items": list(ctx["selected"]), "other": d.get(ctx["step"], {}).get("other")}
    return d[ctx["step"]]