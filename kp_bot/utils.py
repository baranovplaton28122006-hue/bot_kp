"""
utils.py

Утилиты: безопасное редактирование сообщений, форматирование, разное вспомогательное.
(Файл аннотирован автоматически; логика не изменена.)
"""


import html
from threading import Timer
import kp_bot.runtime as runtime
from .config import EMOJI

# [auto]: функция _need_bot_guard()
def _need_bot_guard():
    if runtime.bot is None:
        raise RuntimeError("runtime.bot is not initialized yet")


# [auto]: функция h()
def h(s: str) -> str:
    return html.escape(s or "", quote=False)

# [auto]: функция safe_edit_text()
def safe_edit_text(chat_id: int, message_id: int, text: str, markup=None):
    try:
        runtime.bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except Exception as e:
        s = str(e).lower()
        if "message is not modified" in s:
            return
        if "message to edit not found" in s or "can't be edited" in s:
            runtime.bot.send_message(chat_id, text, reply_markup=markup)
            return
        raise

# [auto]: функция safe_delete()
def safe_delete(chat_id: int, message_id: int):
    try:
        runtime.bot.delete_message(chat_id, message_id)
    except Exception:
        pass

# [auto]: функция send_temp()
def send_temp(chat_id: int, text: str, ttl: int = 5, reply_markup=None):
    msg = runtime.bot.send_message(chat_id, text, reply_markup=reply_markup)
    Timer(ttl, lambda: safe_delete(chat_id, msg.message_id)).start()
    return msg

FRAME = "───────────────────────"

# [auto]: функция framed()
def framed(text: str) -> str:
    return f"{text}"

# [auto]: функция framed_bottom()
def framed_bottom(text: str) -> str:
    return f"{text}\n{FRAME}"