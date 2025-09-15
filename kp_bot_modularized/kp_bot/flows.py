"""
flows.py

Определение сценариев прохождения анкеты: базовый порядок шагов, ветвления по типу решения, а также текущее состояние USER.
(Файл аннотирован автоматически; логика не изменена.)
"""


from typing import Dict, List
import kp_bot.runtime as runtime
from .utils import framed
from .states import St

USER: Dict[int, dict] = {}  # chat_id -> dict

BASE_ORDER = [
    "name", "org_name", "has_site", "has_site_comment",
    "biz_goal", "user_action", "product", "solution",
]
COMMON_ORDER = ["design", "content", "timeline", "contacts", "confirm"]

BRANCH_FLOW = {
    "A": ["A1_blocks", "A2_functions"],
    "B": ["B1_sections", "B2_assort", "B3_functions"],
    "C": ["C1_tasks", "C2_platforms", "C3_integrations"],
    "D": ["D1_goals", "D2_channels", "D4_budget"],
}

BASE_FLOW   = BASE_ORDER.copy()
COMMON_FLOW = COMMON_ORDER.copy()

# [auto]: функция clear_state()
def clear_state(ch: int):
    try:
        runtime.bot.delete_state(ch)
    except Exception:
        pass

# [auto]: функция init_user()
def init_user(ch: int):
    USER[ch] = {
        "idx": 0,
        "flow": BASE_ORDER.copy(),
        "data": {},
        "branch": None,
        "solution": None,
        "multiselect_ctx": {},
        "last_mid": None,
    }

# [auto]: функция get_last_mid()
def get_last_mid(ch: int):
    return USER.get(ch, {}).get("last_mid")

# [auto]: функция set_last_mid()
def set_last_mid(ch: int, mid: int | None):
    if ch in USER:
        USER[ch]["last_mid"] = mid

# [auto]: функция get_flow()
def get_flow(ch: int) -> List[str]:
    return USER[ch]['flow']

# [auto]: функция cur_step()
def cur_step(ch: int) -> str:
    return get_flow(ch)[USER[ch]['idx']]

# [auto]: функция set_step()
def set_step(ch: int, key: str):
    USER[ch]['idx'] = get_flow(ch).index(key)

# [auto]: функция next_step()
def next_step(ch: int):
    USER[ch]['idx'] = min(USER[ch]['idx'] + 1, len(get_flow(ch)) - 1)

# [auto]: функция go_back()
def go_back(ch: int, mid: int | None):
    try:
        st = runtime.bot.get_state(ch, ch)
    except Exception:
        st = None
    st = (st or "").lower()

    from .render import send_step, multiselect_state

    if st.endswith(":other_input"):
        step = multiselect_state(ch).get("step") or cur_step(ch)
        clear_state(ch)
        send_step(ch, step, mid=mid, edit=True)
        return

    if st.endswith(":biz_goal"):
        clear_state(ch)
        send_step(ch, "biz_goal", mid=mid, edit=True)
        return

    if st.endswith(":user_action"):
        clear_state(ch)
        send_step(ch, "user_action", mid=mid, edit=True)
        return

    clear_state(ch)
    USER[ch]["idx"] = max(0, USER[ch]["idx"] - 1)
    send_step(ch, cur_step(ch), mid=mid, edit=True)

# [auto]: функция numbered_title()
def numbered_title(ch: int, step_key: str, text_html: str) -> str:
    return f"{step_no(ch, step_key)}. {text_html}"

STEP_ORDER = [
    "name", "org_name",
    "has_site", "has_site_comment",
    "biz_goal", "user_action", "solution",
    "A1_blocks", "A2_functions",
    "B1_sections", "B2_assort", "B3_functions",
    "C1_tasks", "C2_platforms", "C3_integrations",
    "D1_goals", "D2_channels", "D4_budget",
    "design", "content", "timeline", "contacts", "confirm"
]
STEP_INDEX = {k: i+1 for i, k in enumerate(STEP_ORDER)}

# [auto]: функция render_for_step()
def render_for_step(ch: int, step_key: str) -> str:
    return ""  # скрыть счетчик шага

# [auto]: функция step_no()
def step_no(ch: int, step_key: str) -> int:
    flow = get_flow(ch) if ch in USER else []
    if step_key in flow:
        return flow.index(step_key) + 1
    return USER.get(ch, {}).get("idx", 0) + 1

# [auto]: функция apply_branch_flow()
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
    flow = USER[ch]["flow"]
    if "solution" in flow:
        prefix = flow[:flow.index("solution") + 1]
    else:
        prefix = flow[:]
    USER[ch]["flow"] = prefix + BRANCH_FLOW[b] + COMMON_ORDER
    USER[ch]["idx"] = USER[ch]["flow"].index("solution")