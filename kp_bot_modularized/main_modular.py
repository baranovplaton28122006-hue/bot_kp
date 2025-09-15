"""
main_modular.py

Точка входа в проект (вариант для модульной структуры). Инициализирует пути импорта, конфигурацию логирования и запускает бота.
(Файл аннотирован автоматически; логика не изменена.)
"""


import logging, sys, os, pathlib

# --- Robust path resolution so "kp_bot" imports work regardless of where you place files ---
HERE = pathlib.Path(__file__).resolve()
CANDIDATE_PARENTS = [
    HERE.parent,                          # ./
    HERE.parent / "kp_bot_modular_clean", # ./kp_bot_modular_clean
    HERE.parent.parent,                   # ../
]
for parent in CANDIDATE_PARENTS:
    if (parent / "kp_bot" / "__init__.py").exists():
        sys.path.insert(0, str(parent))
        break

import telebot
from kp_bot.config import TOKEN, PARSE_MODE
from kp_bot.runtime import bot as _bot_ref, log as _log_ref
from kp_bot.handlers import register as register_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# [auto]: функция main()
def main():
    bot = telebot.TeleBot(TOKEN, parse_mode=PARSE_MODE)
    # make bot available to modules
    import kp_bot.runtime as runtime
    runtime.bot = bot

    # register handlers
    register_handlers(bot)

    print("Bot is running…")
    bot.add_custom_filter(telebot.custom_filters.StateFilter(bot))
    bot.infinity_polling(skip_pending=True, allowed_updates=['message','callback_query'])

if __name__ == "__main__":
    main()