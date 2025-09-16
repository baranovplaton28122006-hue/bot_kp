"""
states.py

Определение состояний (telebot State) для пошагового ввода: имя, цели, продукт, комментарии и пр.
(Файл аннотирован автоматически; логика не изменена.)
"""


from telebot.handler_backends import StatesGroup, State

# [auto]: класс St
class St(StatesGroup):
    name = State()
    org_name = State()
    org_category = State()
    has_site = State()
    has_site_comment = State()
    product = State()
    biz_goal = State()
    audience = State()
    user_action = State()
    contacts = State()
    other_input = State()  # универсальный ввод "Свой вариант"