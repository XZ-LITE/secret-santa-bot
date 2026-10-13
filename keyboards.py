from typing import Dict, List, Optional
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_IDS
from custom_emojis import emoji_id

def get_start_keyboard(user_id: int, is_registered: bool = False):
    keyboard = InlineKeyboardBuilder()
    if is_registered:
        keyboard.button(text="Моя анкета и подарок", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
    else:
        keyboard.button(text="Принять участие", callback_data="participate", icon_custom_emoji_id=emoji_id("gift_give"))
        
    keyboard.button(text="Правила и помощь", callback_data="help", icon_custom_emoji_id=emoji_id("info"))
    
    if user_id in ADMIN_IDS:
        keyboard.button(text="Админ-панель", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("crown"))
    
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_gender_keyboard(back_callback: str = "back_to_main"):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Мужской", callback_data="gender_male", icon_custom_emoji_id=emoji_id("user"))
    keyboard.button(text="Женский", callback_data="gender_female", icon_custom_emoji_id=emoji_id("user"))
    keyboard.button(text="Назад", callback_data=back_callback, icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(2, 1)
    return keyboard.as_markup()

def get_wish_link_keyboard(back_callback: str = "back_to_wish_input"):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Без ссылки (пропустить)", callback_data="skip_wish_link", icon_custom_emoji_id=emoji_id("erase"))
    keyboard.button(text="Назад", callback_data=back_callback, icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_back_keyboard(back_callback: str):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", callback_data=back_callback, icon_custom_emoji_id=emoji_id("back"))
    return keyboard.as_markup()

def get_admin_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Статистика", callback_data="admin_stats", icon_custom_emoji_id=emoji_id("stats"))
    keyboard.button(text="Участники", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("users"))
    keyboard.button(text="Распределение", callback_data="admin_distribution_menu", icon_custom_emoji_id=emoji_id("dice"))
    keyboard.button(text="Рассылки", callback_data="admin_broadcasts_menu", icon_custom_emoji_id=emoji_id("megaphone"))
    keyboard.button(text="Экспорт в Excel", callback_data="admin_export_excel", icon_custom_emoji_id=emoji_id("file"))
    keyboard.button(text="Бэкап базы", callback_data="admin_backup", icon_custom_emoji_id=emoji_id("archive"))
    keyboard.button(text="Настройки", callback_data="admin_settings", icon_custom_emoji_id=emoji_id("settings"))
    keyboard.button(text="В главное меню", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(2, 2, 2, 2)
    return keyboard.as_markup()

def get_admin_distribution_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Распределить автоматически", callback_data="admin_distribute_confirm", icon_custom_emoji_id=emoji_id("sparkles"))
    keyboard.button(text="Ручное распределение", callback_data="admin_manual_distribute", icon_custom_emoji_id=emoji_id("puzzle"))
    keyboard.button(text="Статус распределения", callback_data="admin_distribution_status", icon_custom_emoji_id=emoji_id("stats"))
    keyboard.button(text="Сбросить распределение", callback_data="admin_reset_distribution", icon_custom_emoji_id=emoji_id("repeat"))
    keyboard.button(text="Назад в админ-панель", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_admin_broadcasts_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Зарегистрированным", callback_data="admin_notify_all", icon_custom_emoji_id=emoji_id("check"))
    keyboard.button(text="Всем из списка доступа", callback_data="admin_notify_all_users", icon_custom_emoji_id=emoji_id("broadcast"))
    keyboard.button(text="Выбранным участникам", callback_data="admin_notify_selected", icon_custom_emoji_id=emoji_id("user"))
    keyboard.button(text="Отправить напоминания", callback_data="admin_remind", icon_custom_emoji_id=emoji_id("remind"))
    keyboard.button(text="Назад в админ-панель", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_admin_manage_users_keyboard(pending_requests_count: int = 0):
    keyboard = InlineKeyboardBuilder()
    if pending_requests_count > 0:
        keyboard.button(text=f"Заявки на доступ ({pending_requests_count})", callback_data="admin_pending_requests", icon_custom_emoji_id=emoji_id("bell"))
    keyboard.button(text="Список участников", callback_data="admin_users_list", icon_custom_emoji_id=emoji_id("users"))
    keyboard.button(text="Поиск участника", callback_data="admin_search_user", icon_custom_emoji_id=emoji_id("search"))
    keyboard.button(text="Добавить по ID", callback_data="admin_add_user", icon_custom_emoji_id=emoji_id("add_user"))
    keyboard.button(text="Лимит участников", callback_data="admin_set_participants", icon_custom_emoji_id=emoji_id("target"))
    keyboard.button(text="Назад в админ-панель", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("back"))
    
    if pending_requests_count > 0:
        keyboard.adjust(1, 2, 2, 1)
    else:
        keyboard.adjust(2, 2, 1)
    return keyboard.as_markup()

def get_admin_users_list_keyboard(users_list: List[Dict], page: int = 0, per_page: int = 6):
    """Клавиатура интерактивного списка участников с именами и пагинацией"""
    keyboard = InlineKeyboardBuilder()
    total_users = len(users_list)
    total_pages = max(1, (total_users + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_page_users = users_list[start_idx:end_idx]
    
    for u in current_page_users:
        uid = u["id"]
        if u.get("registered"):
            name = u.get("display_name") or u.get("username") or f"ID {uid}"
            key_str = f" #{u['key']}" if u.get("key") else ""
            uname_str = f" (@{u['username']})" if u.get("username") and u["username"] != name else ""
            btn_text = f"{name}{uname_str}{key_str}"
            btn_icon = emoji_id("user")
        else:
            btn_text = f"ID {uid} (не заполнил анкету)"
            btn_icon = emoji_id("hourglass")
        
        if len(btn_text) > 40:
            btn_text = btn_text[:37] + "..."
        keyboard.button(text=btn_text, callback_data=f"admin_user_view_{uid}", icon_custom_emoji_id=btn_icon)
    
    # Кнопки пагинации
    if total_pages > 1:
        if page > 0:
            keyboard.button(text="Назад", callback_data=f"admin_users_page_{page - 1}", icon_custom_emoji_id=emoji_id("back"))
        else:
            keyboard.button(text="•", callback_data="admin_noop")
            
        keyboard.button(text=f"Стр. {page + 1}/{total_pages}", callback_data="admin_noop", icon_custom_emoji_id=emoji_id("file"))
        
        if page < total_pages - 1:
            keyboard.button(text="Вперёд", callback_data=f"admin_users_page_{page + 1}", icon_custom_emoji_id=emoji_id("forward"))
        else:
            keyboard.button(text="•", callback_data="admin_noop")
    
    # Кнопки навигации и поиска
    keyboard.button(text="Поиск", callback_data="admin_search_user", icon_custom_emoji_id=emoji_id("search"))
    keyboard.button(text="Добавить", callback_data="admin_add_user", icon_custom_emoji_id=emoji_id("add_user"))
    keyboard.button(text="В управление", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
    
    layout = [1] * len(current_page_users)
    if total_pages > 1:
        layout.append(3)
    layout.extend([2, 1])
    keyboard.adjust(*layout)
    
    return keyboard.as_markup()

def get_admin_user_card_keyboard(user_id: int | str, is_registered: bool = True):
    """Клавиатура персональной карточки участника с быстрыми действиями"""
    keyboard = InlineKeyboardBuilder()
    if is_registered:
        keyboard.button(text="Изменить имя", callback_data=f"admin_user_edit_name_{user_id}", icon_custom_emoji_id=emoji_id("edit"))
        keyboard.button(text="Сброс лимитов", callback_data=f"admin_user_reset_{user_id}", icon_custom_emoji_id=emoji_id("repeat"))
        keyboard.button(text="Написать в ЛС", callback_data=f"admin_user_msg_{user_id}", icon_custom_emoji_id=emoji_id("message"))
        keyboard.button(text="Удалить из игры", callback_data=f"admin_user_del_confirm_{user_id}", icon_custom_emoji_id=emoji_id("trash"))
    else:
        keyboard.button(text="Напомнить", callback_data=f"admin_user_remind_{user_id}", icon_custom_emoji_id=emoji_id("remind"))
        keyboard.button(text="Написать в ЛС", callback_data=f"admin_user_msg_{user_id}", icon_custom_emoji_id=emoji_id("message"))
        keyboard.button(text="Удалить из доступа", callback_data=f"admin_user_del_confirm_{user_id}", icon_custom_emoji_id=emoji_id("trash"))
    
    keyboard.button(text="К списку участников", callback_data="admin_users_list", icon_custom_emoji_id=emoji_id("users"))
    if is_registered:
        keyboard.adjust(2, 2, 1)
    else:
        keyboard.adjust(2, 1, 1)
    return keyboard.as_markup()

def get_admin_user_del_confirm_keyboard(user_id: int | str):
    """Подтверждение удаления участника"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Да, удалить участника", callback_data=f"admin_user_del_do_{user_id}", icon_custom_emoji_id=emoji_id("trash"))
    keyboard.button(text="Отмена", callback_data=f"admin_user_view_{user_id}", icon_custom_emoji_id=emoji_id("cross"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_admin_settings_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Изменить количество участников", callback_data="admin_set_participants", icon_custom_emoji_id=emoji_id("target"))
    keyboard.button(text="Изменить дедлайн регистрации", callback_data="admin_set_deadline", icon_custom_emoji_id=emoji_id("calendar"))
    keyboard.button(text="Назад", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_help_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    return keyboard.as_markup()

def get_users_keyboard(users_data: Dict, callback_prefix: str = "user_", back_callback: str = "admin_panel"):
    """Создает клавиатуру со списком пользователей"""
    keyboard = InlineKeyboardBuilder()
    
    for user_id_str, user_data in users_data.items():
        display_name = user_data.get("display_name") or user_data.get("username", f"ID {user_id_str}")
        button_text = f"{display_name} (ID: {user_id_str})"
        callback_data = f"{callback_prefix}{user_id_str}"
        keyboard.button(text=button_text, callback_data=callback_data, icon_custom_emoji_id=emoji_id("user"))
    
    keyboard.button(text="Отмена", callback_data=back_callback, icon_custom_emoji_id=emoji_id("cross"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_multi_select_keyboard(users_data: Dict, selected_users: Optional[List[str]] = None, back_callback: str = "admin_panel"):
    """Создает клавиатуру для выбора нескольких пользователей"""
    keyboard = InlineKeyboardBuilder()
    if selected_users is None:
        selected_users = []
    
    for user_id_str, user_data in users_data.items():
        display_name = user_data.get("display_name") or user_data.get("username", f"ID {user_id_str}")
        is_sel = user_id_str in selected_users
        btn_icon = emoji_id("check") if is_sel else emoji_id("user")
        button_text = f"{display_name} (ID: {user_id_str})"
        callback_data = f"select_{user_id_str}"
        keyboard.button(text=button_text, callback_data=callback_data, icon_custom_emoji_id=btn_icon)
    
    if selected_users:
        keyboard.button(text="Продолжить с выбранными", callback_data="continue_with_selected", icon_custom_emoji_id=emoji_id("check"))
    
    keyboard.button(text="Отмена", callback_data=back_callback, icon_custom_emoji_id=emoji_id("cross"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_distribution_confirmation_keyboard():
    """Клавиатура для подтверждения смешанного распределения"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Да, распределить оставшихся автоматически", callback_data="confirm_mixed_distribution", icon_custom_emoji_id=emoji_id("sparkles"))
    keyboard.button(text="Нет, продолжить ручное распределение", callback_data="admin_manual_distribute", icon_custom_emoji_id=emoji_id("puzzle"))
    keyboard.adjust(1)
    return keyboard.as_markup()
