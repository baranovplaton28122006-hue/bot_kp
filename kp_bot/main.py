"""
main.py

Точка входа в пакет kp_bot. Готовит окружение и запускает polling.
(Файл аннотирован автоматически; логика не изменена.)
"""


import sys, os
# Позволяет запускать как "python kp_bot/main.py" (скриптом) И как "python -m kp_bot.main" (модулем)
# Добавляем корень пакета в sys.path при прямом запуске файла
_pkg_root = os.path.dirname(os.path.dirname(__file__))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)

"""Точка входа: создаёт бота, настраивает логирование и регистрирует обработчики."""
import telebot
from kp_bot.config import TOKEN
from kp_bot.logging_setup import setup_logging
from kp_bot.handlers.callbacks import register_callbacks

# [auto]: функция main()
def main():
    log = setup_logging("kp-bot-branch")
    bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

    # Память пользователей (в простом виде — в процессе)
    USER = {}

    # Регистрируем все хендлеры/колбэки
    register_callbacks(bot, USER, log)

    log.info("Bot is running…")
    bot.infinity_polling(skip_pending=True, allowed_updates=['message', 'callback_query'])

if __name__ == "__main__":
    main()
