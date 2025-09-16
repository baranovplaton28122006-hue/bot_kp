"""
config.py

Конфигурация бота, токен, параметры PDF (wkhtmltopdf), тема и эмодзи.
(Файл аннотирован автоматически; логика не изменена.)
"""


import os
import pdfkit

# === TOKEN / BOT CONFIG ===
TOKEN = os.getenv("TELEGRAM_TOKEN", '8068452070:AAFLDvT5HMKOQfhK5tcOD1zAJfmP84cmAvI')
PARSE_MODE = "HTML"

# === PDF config (same path as original) ===
path_wkhtmltopdf = r"C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe"
pdf_config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

# === UI theme & emojis ===
THEME = {"brand": "#2c5aa0", "muted": "#6b7280", "accent": "#10b981"}
EMOJI = {"start": "📝", "about": "ℹ️", "back": "⬅️", "home": "🏠", "ok": "✅", "no": "❌", "edit": "✍️",
         "confirm": "✔️", "info": "📋", "check": "☑️", "empty": "⬜"}

# Pagination size for option lists
PAGE_SIZE = 5