import os
import re
import html
import datetime
import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, GIFT_BUDGET
from database import db
from states import (
    AdminAddUser,
    AdminRemoveUser,
    AdminSetParticipants,
    AdminSearchUser,
    AdminSetDeadline,
    AdminNotifyAll,
    AdminNotifyAllUsers,
    AdminEditDisplayName,
    AdminManualDistribution,
    AdminNotifySelected,
    AdminDirectMessage
)
from keyboards import (
    get_admin_keyboard,
    get_admin_distribution_keyboard,
    get_admin_broadcasts_keyboard,
    get_admin_manage_users_keyboard,
    get_admin_settings_keyboard,
    get_admin_anonymity_keyboard,
    get_back_keyboard,
    get_users_keyboard,
    get_multi_select_keyboard,
    get_distribution_confirmation_keyboard,
    get_admin_users_list_keyboard,
    get_admin_user_card_keyboard,
    get_admin_user_del_confirm_keyboard,
    get_broadcast_preview_keyboard
)
from utils import (
    is_registration_open,
    format_admin_user_card,
    format_wish_links,
    format_recipient_info_for_santa,
    send_message_safe
)
from custom_emojis import (
    E_USER, E_USERS, E_GIFT, E_GIFT_STAR, E_CHECK, E_CROSS,
    E_HOURGLASS, E_CALENDAR, E_CLOCK, E_MONEY, E_PARTY,
    E_EDIT, E_LINK, E_SPARKLES, E_STATS, E_WARNING,
    E_BELL, E_MESSAGE, E_INFO, E_FILE, E_ARCHIVE, E_TARGET,
    E_CROWN, E_DICE, E_PUZZLE, E_MEGAPHONE, E_BROADCAST, E_SETTINGS,
    E_ADD_USER, E_SEARCH, E_LOCK, emoji_id, render_text_with_custom_emojis
)
from services.notifications import notify_all_participants

admin_router = Router(name="admin")

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Быстрый переход в админ-панель по команде /admin"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(f"{E_CROSS} У вас нет прав администратора.", parse_mode="HTML")
        return
    await state.clear()
    is_open, time_left_msg = is_registration_open()
    deadline = await db.get_registration_deadline()
    
    await message.answer(
        f"{E_CROWN} <b>Панель администратора Тайного Санты</b>\n\n"
        f"{E_CALENDAR} <b>Дедлайн:</b> {deadline.strftime('%d.%m.%Y %H:%M')}\n"
        f"{time_left_msg}",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery, state: FSMContext):
    """Панель администратора"""
    await state.clear()
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа к админ-панели", show_alert=True)
        return
    
    is_open, time_left_msg = is_registration_open()
    deadline = await db.get_registration_deadline()
    
    await callback.message.edit_text(
        f"{E_CROWN} <b>Панель администратора Тайного Санты</b>\n\n"
        f"{E_CALENDAR} <b>Дедлайн:</b> {deadline.strftime('%d.%m.%Y %H:%M')}\n"
        f"{time_left_msg}",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Статистика участников"""
    count = await db.get_participants_count()
    total_participants = await db.get_total_participants()
    distribution_status = await db.get_distribution_status()
    unregistered = await db.get_unregistered_users()
    allowed_users = await db.get_allowed_users()
    
    is_open, time_left_msg = is_registration_open()
    deadline = await db.get_registration_deadline()
    
    not_added_count = max(0, total_participants - len(allowed_users))
    text = (
        f"{E_STATS} <b>Статистика участников:</b>\n"
        f"• Зарегистрировано анкет: <b>{count}/{total_participants}</b> участников\n"
        f"• В списке доступа (whitelist): <b>{len(allowed_users)}</b> чел.\n"
        f"• Ожидают регистрации из списка: <b>{len(unregistered)}</b> чел.\n"
    )
    if not_added_count > 0:
        text += f"• Ещё не добавлены в доступ: <b>{not_added_count}</b> чел.\n"
    
    text += (
        f"\n{E_GIFT} <b>Статус распределения:</b>\n<i>{distribution_status}</i>\n\n"
        f"{E_CALENDAR} <b>Дедлайн:</b> {deadline.strftime('%d.%m.%Y %H:%M')}\n"
        f"{E_MONEY} <b>Бюджет подарка:</b> {GIFT_BUDGET} рублей\n\n"
        f"{time_left_msg}"
    )
    
    if not_added_count > 0:
        text += (
            f"\n\n{E_WARNING} <b>ВНИМАНИЕ:</b>\n"
            f"В списке доступа только {len(allowed_users)} пользователей, а нужно {total_participants}.\n"
            f"Добавьте остальных {not_added_count} чел. через раздел участников или попросите их подать заявку в боте."
        )
    elif unregistered:
        text += f"\n\n{E_FILE} <b>Ожидающие регистрации пользователи (ID):</b>\n"
        for uid in unregistered[:10]:
            text += f"• <code>{uid}</code>\n"
        if len(unregistered) > 10:
            text += f"• ... и еще {len(unregistered) - 10}"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("back"))
    keyboard.button(text="Отправить напоминания", callback_data="admin_remind", icon_custom_emoji_id=emoji_id("remind"))
    keyboard.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_manage_users")
async def admin_manage_users(callback: CallbackQuery, state: FSMContext):
    """Управление участниками"""
    await state.clear()
    requests = await db.get_all_access_requests()
    pending_count = len(requests)
    text = f"{E_USERS} <b>Управление участниками</b>\n\nВыберите действие:"
    if pending_count > 0:
        text += f"\n\n{E_BELL} Ожидают одобрения заявок: <b>{pending_count}</b>"
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_manage_users_keyboard(pending_count),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_pending_requests")
async def admin_pending_requests(callback: CallbackQuery):
    """Просмотр ожидающих заявок на доступ"""
    requests = await db.get_all_access_requests()
    if not requests:
        await callback.message.edit_text(
            f"{E_INFO} Нет ожидающих заявок на доступ.",
            reply_markup=get_back_keyboard("admin_manage_users"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    keyboard = InlineKeyboardBuilder()
    text = f"{E_BELL} <b>Ожидающие заявки на доступ ({len(requests)}):</b>\n\n"
    for uid_str, req_data in requests.items():
        name = req_data.get("full_name", f"ID {uid_str}")
        if req_data.get("username"):
            name += f" (@{req_data['username']})"
        text += f"• {name} (<code>ID: {uid_str}</code>)\n"
        keyboard.button(text=f"Одобрить {name[:12]}", callback_data=f"approve_user_{uid_str}", icon_custom_emoji_id=emoji_id("check"))
        keyboard.button(text=f"Отклонить {name[:12]}", callback_data=f"reject_user_{uid_str}", icon_custom_emoji_id=emoji_id("cross"))
    
    keyboard.button(text="Назад", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(2)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("approve_user_"))
async def admin_approve_user(callback: CallbackQuery, bot: Bot):
    """Одобрение заявки на доступ"""
    user_id_str = callback.data.replace("approve_user_", "")
    user_id = int(user_id_str)
    
    req_data = await db.get_access_request(user_id)
    await db.remove_access_request(user_id)
    await db.add_allowed_user(user_id)
    
    user_name = f"ID {user_id}"
    if req_data:
        user_name = req_data.get("full_name") or user_name
        if req_data.get("username"):
            user_name += f" (@{req_data['username']})"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="В панель управления", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
    
    await callback.message.edit_text(
        f"{E_CHECK} <b>Заявка одобрена!</b>\n\n"
        f"{E_USER} Пользователь: {user_name}\n"
        f"• ID: <code>{user_id}</code>\n\n"
        f"Пользователь добавлен в список разрешенных участников.",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer("Пользователь одобрен!")
    
    msg = (
        f"{E_PARTY} <b>Ваша заявка на участие в Тайном Санте одобрена!</b>\n\n"
        "Теперь вы можете зарегистрироваться. Нажмите /start, чтобы начать участие!"
    )
    await send_message_safe(bot, user_id, msg, parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("reject_user_"))
async def admin_reject_user(callback: CallbackQuery, bot: Bot):
    """Отклонение заявки на доступ"""
    user_id_str = callback.data.replace("reject_user_", "")
    user_id = int(user_id_str)
    
    req_data = await db.get_access_request(user_id)
    await db.remove_access_request(user_id)
    
    user_name = f"ID {user_id}"
    if req_data:
        user_name = req_data.get("full_name") or user_name
        if req_data.get("username"):
            user_name += f" (@{req_data['username']})"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="В панель управления", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
    
    await callback.message.edit_text(
        f"{E_CROSS} <b>Заявка отклонена.</b>\n\n"
        f"{E_USER} Пользователь: {user_name}\n"
        f"• ID: <code>{user_id}</code>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer("Заявка отклонена.")
    
    msg = f"{E_CROSS} Ваша заявка на участие в Тайном Санте была отклонена администратором."
    await send_message_safe(bot, user_id, msg, parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_add_user")
async def admin_add_user_menu(callback: CallbackQuery, state: FSMContext):
    """Добавление участника"""
    allowed_users = await db.get_allowed_users()
    total_participants = await db.get_total_participants()
    
    await callback.message.edit_text(
        f"{E_ADD_USER} <b>Добавление участника</b>\n\n"
        f"{E_STATS} <b>Текущая ситуация:</b>\n"
        f"• Нужно участников: <b>{total_participants}</b>\n"
        f"• В списке доступа: <b>{len(allowed_users)}</b>\n"
        f"• Не хватает: <b>{max(0, total_participants - len(allowed_users))}</b>\n\n"
        f"Отправьте Telegram ID пользователя для добавления:\n"
        "(ID можно получить у пользователя или использовать @username)\n\n"
        "Просто отправьте ID или нажмите «Назад»:",
        reply_markup=get_back_keyboard("admin_manage_users"),
        parse_mode="HTML"
    )
    await state.set_state(AdminAddUser.entering_user_id)
    await callback.answer()

@admin_router.message(AdminAddUser.entering_user_id)
async def admin_add_user_process(message: Message, state: FSMContext):
    """Обработка добавления пользователя"""
    user_input = message.text.strip()
    
    if user_input.startswith('@'):
        username = user_input[1:].lower()
        # Проверяем заявки на доступ
        requests = await db.get_all_access_requests()
        matched_uid = None
        for uid_str, rdata in requests.items():
            if (rdata.get("username") or "").lower() == username:
                matched_uid = int(uid_str)
                break
        
        if matched_uid:
            await db.remove_access_request(matched_uid)
            await db.add_allowed_user(matched_uid)
            await state.clear()
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="Открыть карточку", callback_data=f"admin_user_view_{matched_uid}", icon_custom_emoji_id=emoji_id("user"))
            keyboard.button(text="Список участников", callback_data="admin_users_list", icon_custom_emoji_id=emoji_id("users"))
            keyboard.adjust(1)
            await message.answer(
                f"{E_PARTY} Найдена заявка от <b>@{username}</b> (<code>ID: {matched_uid}</code>)!\n\n"
                f"Заявка автоматически одобрена, пользователь добавлен в игру.",
                reply_markup=keyboard.as_markup(),
                parse_mode="HTML"
            )
            return

        await message.answer(
            f"{E_INFO} Бот пока не встречал пользователя <b>@{username}</b>.\n\n"
            f"Чтобы добавить его, есть два простых варианта:\n"
            f"1. Попросите его перейти в бота и нажать <i>«Подать заявку на участие»</i> — вам сразу придет кнопка подтверждения.\n"
            f"2. Или отправьте его числовой Telegram ID (его можно узнать через @userinfobot).",
            parse_mode="HTML"
        )
        return
    elif user_input.isdigit():
        user_id = int(user_input)
    else:
        await message.answer(f"{E_CROSS} Пожалуйста, введите числовой Telegram ID", parse_mode="HTML")
        return
    
    allowed_users = await db.get_allowed_users()
    if user_id in allowed_users:
        await message.answer(f"{E_CROSS} Пользователь с ID <code>{user_id}</code> уже добавлен", parse_mode="HTML")
    else:
        success = await db.add_allowed_user(user_id)
        if success:
            total_participants = await db.get_total_participants()
            await message.answer(
                f"{E_CHECK} Пользователь с ID <code>{user_id}</code> успешно добавлен!\n\n"
                f"{E_STATS} Теперь в списке доступа: <b>{len(allowed_users) + 1}</b> пользователей\n"
                f"{E_TARGET} Целевое количество: <b>{total_participants}</b>",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"{E_CROSS} Ошибка при добавлении пользователя", parse_mode="HTML")
    
    await state.clear()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
    await message.answer("Выберите действие:", reply_markup=keyboard.as_markup(), parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_remove_user")
async def admin_remove_user_menu(callback: CallbackQuery, state: FSMContext):
    """Удаление участника"""
    allowed_users = await db.get_allowed_users()
    if not allowed_users:
        await callback.message.edit_text(
            f"{E_CROSS} Список участников пуст",
            reply_markup=get_back_keyboard("admin_manage_users"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    text = f"{E_CROSS} <b>Удаление участника</b>\n\nТекущие участники:\n"
    for i, user_id in enumerate(allowed_users[:20], 1):
        text += f"{i}. ID: <code>{user_id}</code>\n"
    if len(allowed_users) > 20:
        text += f"... и еще {len(allowed_users) - 20}\n"
    text += "\nОтправьте ID пользователя для удаления:"
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard("admin_manage_users"), parse_mode="HTML")
    await state.set_state(AdminRemoveUser.entering_user_id)
    await callback.answer()

@admin_router.message(AdminRemoveUser.entering_user_id)
async def admin_remove_user_process(message: Message, state: FSMContext):
    """Обработка удаления пользователя"""
    user_input = message.text.strip()
    if not user_input.isdigit():
        await message.answer(f"{E_CROSS} Пожалуйста, введите числовой Telegram ID", parse_mode="HTML")
        return
    
    user_id = int(user_input)
    allowed_users = await db.get_allowed_users()
    
    if user_id not in allowed_users:
        await message.answer(f"{E_CROSS} Пользователь с ID <code>{user_id}</code> не найден в списке", parse_mode="HTML")
    elif user_id in ADMIN_IDS:
        await message.answer(f"{E_CROSS} Нельзя удалить администратора!", parse_mode="HTML")
    else:
        success = await db.remove_allowed_user(user_id)
        if success:
            await message.answer(
                f"{E_CHECK} Пользователь с ID <code>{user_id}</code> успешно удален!\n"
                f"Также удалены все его данные о регистрации и желаниях.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"{E_CROSS} Нельзя удалить зарегистрированного участника после начала распределения. "
                "Сначала сбросьте распределение.",
                parse_mode="HTML"
            )
    
    await state.clear()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
    await message.answer("Выберите действие:", reply_markup=keyboard.as_markup(), parse_mode="HTML")

async def _build_admin_users_list():
    users = await db.get_all_users()
    allowed_users = await db.get_allowed_users()
    
    users_list = []
    seen_ids = set()
    
    # 1. Зарегистрированные участники
    for uid_str, udata in users.items():
        uid = int(uid_str)
        users_list.append({
            "id": uid,
            "registered": True,
            "display_name": udata.get("display_name", ""),
            "username": udata.get("username", ""),
            "key": udata.get("key"),
            "user_data": udata
        })
        seen_ids.add(uid)
        
    # 2. Ожидающие регистрации из белого списка
    for uid in allowed_users:
        if uid not in seen_ids:
            users_list.append({
                "id": uid,
                "registered": False,
                "display_name": "",
                "username": "",
                "key": None,
                "user_data": None
            })
    return users_list

@admin_router.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery, state: FSMContext):
    """Интерактивный список участников с карточками"""
    await state.clear()
    users_list = await _build_admin_users_list()
    if not users_list:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Добавить участника", callback_data="admin_add_user", icon_custom_emoji_id=emoji_id("add_user"))
        keyboard.button(text="Назад", callback_data="admin_manage_users", icon_custom_emoji_id=emoji_id("back"))
        keyboard.adjust(1)
        await callback.message.edit_text(f"{E_INFO} Список участников пуст.", reply_markup=keyboard.as_markup(), parse_mode="HTML")
        await callback.answer()
        return
    
    count = await db.get_participants_count()
    total = await db.get_total_participants()
    text = (
        f"{E_USERS} <b>Управление участниками</b>\n\n"
        f"• Зарегистрировано анкет: <b>{count}/{total}</b> чел.\n"
        f"• Всего в списке доступа: <b>{len(users_list)}</b> чел.\n\n"
        f"Нажмите на любого участника, чтобы открыть его карточку и управлять им:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_users_list_keyboard(users_list, page=0),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_page(callback: CallbackQuery):
    """Переключение страницы списка участников"""
    page = int(callback.data.replace("admin_users_page_", ""))
    users_list = await _build_admin_users_list()
    count = await db.get_participants_count()
    total = await db.get_total_participants()
    text = (
        f"{E_USERS} <b>Управление участниками</b>\n\n"
        f"• Зарегистрировано анкет: <b>{count}/{total}</b> чел.\n"
        f"• Всего в списке доступа: <b>{len(users_list)}</b> чел.\n\n"
        f"Нажмите на любого участника, чтобы открыть его карточку:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_users_list_keyboard(users_list, page=page),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_user_view_"))
async def admin_user_view(callback: CallbackQuery, state: FSMContext):
    """Просмотр карточки участника"""
    await state.clear()
    uid = int(callback.data.replace("admin_user_view_", ""))
    user_data = await db.get_user(uid)
    is_registered = user_data is not None and user_data.get("registered", False)
    all_users = await db.get_all_users()
    
    text = format_admin_user_card(
        user_id=uid,
        user_data=user_data,
        is_registered=is_registered,
        all_users=all_users
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_user_card_keyboard(uid, is_registered=is_registered),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_user_edit_name_"))
async def admin_user_edit_name(callback: CallbackQuery, state: FSMContext):
    """Запрос нового имени для участника"""
    uid = int(callback.data.replace("admin_user_edit_name_", ""))
    user_data = await db.get_user(uid)
    current_name = (user_data.get("display_name") or user_data.get("username") or f"ID {uid}") if user_data else f"ID {uid}"
    
    await state.update_data(user_id=uid)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Отмена", callback_data=f"admin_user_view_{uid}", icon_custom_emoji_id=emoji_id("cross"))
    
    await callback.message.edit_text(
        f"{E_EDIT} <b>Изменение имени участника</b>\n\n"
        f"Текущее имя: <b>{current_name}</b> (<code>ID: {uid}</code>)\n\n"
        f"Введите новое реальное имя и фамилию (например, <i>Иван Иванов</i>):",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AdminEditDisplayName.entering_display_name)
    await callback.answer()

@admin_router.message(AdminEditDisplayName.entering_display_name)
async def admin_edit_display_name_process(message: Message, state: FSMContext):
    """Сохранение нового имени участника"""
    display_name = message.text.strip()
    state_data = await state.get_data()
    user_id = state_data.get("user_id")
    
    if not user_id:
        await message.answer(f"{E_CROSS} Ошибка: не найден ID пользователя", parse_mode="HTML")
        await state.clear()
        return
    
    success = await db.update_display_name(user_id, display_name)
    await state.clear()
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Вернуться к карточке", callback_data=f"admin_user_view_{user_id}", icon_custom_emoji_id=emoji_id("user"))
    keyboard.button(text="Список участников", callback_data="admin_users_list", icon_custom_emoji_id=emoji_id("users"))
    keyboard.adjust(1)
    
    if success:
        await message.answer(
            f"{E_CHECK} Имя участника успешно обновлено на: <b>{display_name}</b>!",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
    else:
        await message.answer(f"{E_CROSS} Ошибка при обновлении имени пользователя.", reply_markup=keyboard.as_markup(), parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("admin_user_reset_"))
async def admin_user_reset(callback: CallbackQuery):
    """Сброс лимитов изменений участника в 1 клик"""
    uid = int(callback.data.replace("admin_user_reset_", ""))
    success = await db.reset_user_changes(uid, "all")
    if success:
        await callback.answer("Лимиты изменений успешно сброшены!", show_alert=True)
    else:
        await callback.answer("Не удалось сбросить лимиты (возможно, распределение уже завершено)", show_alert=True)
    
    user_data = await db.get_user(uid)
    all_users = await db.get_all_users()
    text = format_admin_user_card(
        user_id=uid,
        user_data=user_data,
        is_registered=True,
        all_users=all_users
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_user_card_keyboard(uid, is_registered=True),
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data.startswith("admin_user_remind_"))
async def admin_user_remind_one(callback: CallbackQuery, bot: Bot):
    """Персональное напоминание незарегистрированному пользователю"""
    uid = int(callback.data.replace("admin_user_remind_", ""))
    deadline = await db.get_registration_deadline()
    msg = (
        f"{E_BELL} <b>Персональное напоминание от Тайного Санты!</b>\n\n"
        f"Вы включены в список участников игры. Пожалуйста, не забудьте зарегистрироваться до <b>{deadline.strftime('%d.%m.%Y %H:%M')}</b>!\n\n"
        f"Нажмите /start, чтобы заполнить короткую анкету и загадать подарок."
    )
    success, _ = await send_message_safe(bot, uid, msg, parse_mode="HTML")
    if success:
        await db.update_last_reminder(uid)
        await callback.answer("Персональное напоминание отправлено!", show_alert=True)
    else:
        await callback.answer("Не удалось отправить (пользователь ещё ни разу не запускал бота)", show_alert=True)

@admin_router.callback_query(F.data.startswith("admin_user_msg_"))
async def admin_user_msg_start(callback: CallbackQuery, state: FSMContext):
    """Отправка личного сообщения участнику"""
    uid = int(callback.data.replace("admin_user_msg_", ""))
    user_data = await db.get_user(uid)
    name = (user_data.get("display_name") or user_data.get("username") or f"ID {uid}") if user_data else f"ID {uid}"
    
    await state.update_data(target_user_id=uid, target_user_name=name)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Отмена", callback_data=f"admin_user_view_{uid}", icon_custom_emoji_id=emoji_id("cross"))
    
    await callback.message.edit_text(
        f"{E_MESSAGE} <b>Личное сообщение участнику</b>\n\n"
        f"Получатель: <b>{name}</b> (<code>ID: {uid}</code>)\n\n"
        f"Отправьте текст сообщения или <b>фотографию с подписью</b>:\n\n"
        f"<blockquote>• Премиум эмодзи: выберите в клавиатуре или укажите шорткод (например, <code>:gift:</code>, <code>:party:</code>, <code>:star:</code>, <code>:bell:</code>)\n"
        f"• Форматирование: жирный, курсив, цитаты, спойлеры\n"
        f"• Перед отправкой будет доступен предпросмотр</blockquote>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AdminDirectMessage.entering_message)
    await callback.answer()

@admin_router.message(AdminDirectMessage.entering_message)
async def admin_user_msg_send(message: Message, state: FSMContext):
    """Предпросмотр личного сообщения участнику"""
    state_data = await state.get_data()
    uid = state_data.get("target_user_id")
    name = state_data.get("target_user_name", f"ID {uid}")
    
    if not uid:
        await message.answer(f"{E_CROSS} Ошибка: не найден получатель.", parse_mode="HTML")
        await state.clear()
        return
    
    await prepare_and_show_broadcast_preview(
        message=message,
        state=state,
        recipient_ids=[int(uid)],
        target_desc=f"{name} (ID: {uid})",
        header=f"{E_MESSAGE} <b>Личное сообщение от организатора Тайного Санты:</b>",
        cancel_callback=f"admin_user_view_{uid}",
        back_state=AdminDirectMessage.entering_message
    )
    await state.set_state(AdminDirectMessage.confirming)

@admin_router.callback_query(F.data.startswith("admin_user_del_confirm_"))
async def admin_user_del_confirm(callback: CallbackQuery):
    """Подтверждение удаления участника"""
    uid = int(callback.data.replace("admin_user_del_confirm_", ""))
    if uid in ADMIN_IDS:
        await callback.answer("Нельзя удалить администратора!", show_alert=True)
        return
    
    user_data = await db.get_user(uid)
    name = (user_data.get("display_name") or user_data.get("username") or f"ID {uid}") if user_data else f"ID {uid}"
    
    text = (
        f"{E_WARNING} <b>Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите удалить участника <b>{name}</b> (<code>ID: {uid}</code>) из Тайного Санты?\n\n"
        f"Его анкета, желания и доступ к игре будут полностью аннулированы."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_user_del_confirm_keyboard(uid),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_user_del_do_"))
async def admin_user_del_do(callback: CallbackQuery):
    """Выполнение удаления участника"""
    uid = int(callback.data.replace("admin_user_del_do_", ""))
    if uid in ADMIN_IDS:
        await callback.answer("Нельзя удалить администратора!", show_alert=True)
        return
    
    success = await db.remove_allowed_user(uid)
    if success:
        await callback.answer("Участник успешно удалён!", show_alert=True)
    else:
        await callback.answer("Нельзя удалить участника после распределения (сначала сбросьте распределение)", show_alert=True)
    
    users_list = await _build_admin_users_list()
    count = await db.get_participants_count()
    total = await db.get_total_participants()
    text = (
        f"{E_USERS} <b>Управление участниками</b>\n\n"
        f"• Зарегистрировано анкет: <b>{count}/{total}</b> чел.\n"
        f"• Всего в списке доступа: <b>{len(users_list)}</b> чел.\n\n"
        f"Нажмите на любого участника, чтобы открыть его карточку:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_users_list_keyboard(users_list, page=0),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data.in_({"admin_remove_user", "admin_edit_display_name", "admin_reset_changes"}))
async def admin_redirect_to_users_list(callback: CallbackQuery, state: FSMContext):
    """Перенаправление устаревших меню в интерактивный список участников"""
    await callback.answer()
    await admin_users_list(callback, state)

@admin_router.callback_query(F.data == "admin_noop")
async def admin_noop(callback: CallbackQuery):
    """Пустой обработчик для информационных кнопок пагинации"""
    await callback.answer()

@admin_router.callback_query(F.data == "admin_set_participants")
async def admin_set_participants_menu(callback: CallbackQuery, state: FSMContext):
    """Установка количества участников"""
    current_count = await db.get_total_participants()
    allowed_users = await db.get_allowed_users()
    
    await callback.message.edit_text(
        f"{E_TARGET} <b>Установка количества участников</b>\n\n"
        f"Текущее количество: <b>{current_count}</b>\n"
        f"Пользователей в списке доступа: <b>{len(allowed_users)}</b>\n\n"
        f"Введите новое количество участников (от 2 до 500):",
        reply_markup=get_back_keyboard("admin_manage_users"),
        parse_mode="HTML"
    )
    await state.set_state(AdminSetParticipants.entering_count)
    await callback.answer()

@admin_router.message(AdminSetParticipants.entering_count)
async def admin_set_participants_process(message: Message, state: FSMContext):
    """Обработка установки количества участников"""
    user_input = message.text.strip()
    if not user_input.isdigit():
        await message.answer(f"{E_CROSS} Пожалуйста, введите число", parse_mode="HTML")
        return
    
    new_count = int(user_input)
    if new_count < 2 or new_count > 500:
        await message.answer(f"{E_CROSS} Количество участников должно быть от 2 до 500", parse_mode="HTML")
        return
    
    registered_count = await db.get_participants_count()
    if new_count < registered_count:
        await message.answer(
            f"{E_CROSS} Нельзя установить количество меньше уже зарегистрированных участников!\n"
            f"Сейчас зарегистрировано: <b>{registered_count}</b> участников.",
            parse_mode="HTML"
        )
        return
    
    await db.set_total_participants(new_count)
    allowed_users = await db.get_allowed_users()
    registered_count = await db.get_participants_count()
    
    await message.answer(
        f"{E_CHECK} <b>Количество участников изменено!</b>\n\n"
        f"{E_TARGET} Новое количество: <b>{new_count}</b>\n\n"
        f"{E_STATS} <b>Статистика:</b>\n"
        f"• Зарегистрировано: <b>{registered_count}/{new_count}</b>\n"
        f"• В списке доступа: <b>{len(allowed_users)}</b> пользователей\n"
        f"• Не хватает пользователей: <b>{max(0, new_count - len(allowed_users))}</b>",
        parse_mode="HTML"
    )
    
    await state.clear()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_manage_users")
    await message.answer("Выберите действие:", reply_markup=keyboard.as_markup())

@admin_router.callback_query(F.data == "admin_search_user")
async def admin_search_user_menu(callback: CallbackQuery, state: FSMContext):
    """Поиск участника"""
    await callback.message.edit_text(
        f"{E_SEARCH} <b>Поиск участника</b>\n\n"
        "Отправьте любое из значений:\n"
        "• Имя или фамилию (например: <i>Иван</i> или <i>Смирнова</i>)\n"
        "• Telegram @username (например: <i>@ivanov</i>)\n"
        "• Секретный ключ (например: <i>10001</i> или <i>#10001</i>)\n"
        "• Telegram ID (например: <i>123456789</i>)\n"
        "• Часть желаемого подарка (например: <i>наушники</i>)\n\n"
        "Введите поисковый запрос:",
        reply_markup=get_back_keyboard("admin_manage_users"),
        parse_mode="HTML"
    )
    await state.set_state(AdminSearchUser.entering_query)
    await callback.answer()

@admin_router.message(AdminSearchUser.entering_query)
async def admin_search_user_process(message: Message, state: FSMContext):
    """Обработка поиска участника"""
    query = message.text.strip()
    if not query:
        await message.answer(f"{E_CROSS} Пожалуйста, введите запрос для поиска", parse_mode="HTML")
        return
    
    results = await db.search_users(query)
    if not results:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Попробовать снова", icon_custom_emoji_id=emoji_id("search"), callback_data="admin_search_user")
        keyboard.button(text="Список участников", icon_custom_emoji_id=emoji_id("users"), callback_data="admin_users_list")
        keyboard.adjust(1)
        await message.answer(f"{E_CROSS} По запросу «<b>{query}</b>» участники не найдены.", reply_markup=keyboard.as_markup(), parse_mode="HTML")
        await state.clear()
        return
    
    keyboard = InlineKeyboardBuilder()
    for uid_str, udata in results[:10]:
        uid = int(uid_str)
        if udata.get("registered", True):
            name = udata.get("display_name") or udata.get("username") or f"ID {uid}"
            key_str = f" #{udata.get('key')}" if udata.get("key") else ""
            raw_u = (udata.get("username") or "").strip().lstrip('@')
            uname_str = f" (@{raw_u})" if raw_u and re.match(r'^[a-zA-Z0-9_]{3,32}$', raw_u) and raw_u != name else ""
            btn_text = f"{name}{uname_str}{key_str}"
            btn_icon = emoji_id("user")
        else:
            btn_text = f"ID {uid} (не заполнил анкету)"
            btn_icon = emoji_id("hourglass")
        
        if len(btn_text) > 40:
            btn_text = btn_text[:37] + "..."
        keyboard.button(text=btn_text, icon_custom_emoji_id=btn_icon, callback_data=f"admin_user_view_{uid}")
    
    keyboard.button(text="Новый поиск", icon_custom_emoji_id=emoji_id("search"), callback_data="admin_search_user")
    keyboard.button(text="Список участников", icon_custom_emoji_id=emoji_id("users"), callback_data="admin_users_list")
    keyboard.adjust(*( [1] * min(len(results), 10) + [1, 1] ))
    
    await message.answer(
        f"{E_SEARCH} Найдено участников по запросу «<b>{query}</b>»: <b>{len(results)}</b>\n\n"
        f"Нажмите на участника, чтобы открыть его карточку и управлять им:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await state.clear()

@admin_router.callback_query(F.data == "admin_export_excel")
async def admin_export_excel(callback: CallbackQuery, bot: Bot):
    """Экспорт данных в Excel"""
    await callback.message.edit_text(f"{E_ARCHIVE} Экспорт данных в Excel...", parse_mode="HTML")
    try:
        excel_path = await db.export_to_excel()
        excel_file = FSInputFile(excel_path)
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=excel_file,
            caption=f"{E_STATS} <b>Экспорт данных Тайного Санты в Excel</b>\n"
                   f"{E_CALENDAR} Дата: <b>{datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}</b>\n"
                   f"{E_USERS} Участников: <b>{await db.get_participants_count()}/{await db.get_total_participants()}</b>\n"
                   f"{E_MONEY} Бюджет: <b>{GIFT_BUDGET} рублей</b>",
            parse_mode="HTML"
        )
        try:
            os.remove(excel_path)
        except OSError:
            pass
        await callback.message.edit_text(
            f"{E_CHECK} Данные успешно экспортированы в Excel!",
            reply_markup=get_back_keyboard("admin_manage_users"),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"{E_CROSS} Ошибка при экспорте в Excel: {html.escape(str(e), quote=False)}",
            reply_markup=get_back_keyboard("admin_manage_users"),
            parse_mode="HTML"
        )
    
    await callback.answer()

@admin_router.callback_query(F.data == "admin_backup")
async def admin_backup(callback: CallbackQuery, bot: Bot):
    """Резервное копирование базы данных"""
    await callback.message.edit_text(f"{E_FILE} Создание резервной копии...", parse_mode="HTML")
    try:
        backup_path = await db.create_backup()
        backup_file = FSInputFile(backup_path)
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=backup_file,
            caption=f"{E_FILE} <b>Резервная копия базы данных</b>\n"
                   f"{E_CALENDAR} Дата: <b>{datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}</b>\n"
                   f"{E_USERS} Участников: <b>{await db.get_participants_count()}/{await db.get_total_participants()}</b>",
            parse_mode="HTML"
        )
        await callback.message.edit_text(
            f"{E_CHECK} Резервная копия успешно создана и отправлена!",
            reply_markup=get_back_keyboard("admin_manage_users"),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"{E_CROSS} Ошибка при создании резервной копии: {html.escape(str(e), quote=False)}",
            reply_markup=get_back_keyboard("admin_manage_users"),
            parse_mode="HTML"
        )
    
    await callback.answer()

@admin_router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery, state: FSMContext):
    """Настройки"""
    await state.clear()
    current_count = await db.get_total_participants()
    deadline = await db.get_registration_deadline()
    allowed_users = await db.get_allowed_users()
    anon_mode = await db.get_anonymity_mode()
    mode_name = {"code": "Код (#10001)", "name": "По имени", "gender": "По полу"}.get(anon_mode, anon_mode)
    is_mod = await db.is_moderation_enabled()
    is_filter = await db.is_filter_enabled()
    is_chat = await db.is_chat_enabled()
    
    text = (
        f"{E_SETTINGS} <b>Настройки бота</b>\n\n"
        f"{E_TARGET} Количество участников: <b>{current_count}</b>\n"
        f"{E_USERS} Пользователей в списке доступа: <b>{len(allowed_users)}</b>\n"
        f"{E_CLOCK} Регистрация открыта до: <b>{deadline.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"{E_MONEY} Бюджет подарка: <b>{GIFT_BUDGET} рублей</b>\n\n"
        f"{E_LOCK} <b>Приватность и переписка:</b>\n"
        f"• Режим подопечного: <b>{mode_name}</b>\n"
        f"• Фильтр стоп-слов: <b>{'ВКЛ' if is_filter else 'ВЫКЛ'}</b>\n"
        f"• Премодерация записок: <b>{'ВКЛ' if is_mod else 'ВЫКЛ'}</b>\n"
        f"• Анонимный чат: <b>{'ВКЛ' if is_chat else 'ВЫКЛ'}</b>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_settings_keyboard(moderation_enabled=is_mod), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_anonymity_menu")
async def admin_anonymity_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления анонимностью, фильтрами и чатом"""
    await state.clear()
    mode = await db.get_anonymity_mode()
    is_filter = await db.is_filter_enabled()
    is_mod = await db.is_moderation_enabled()
    is_chat = await db.is_chat_enabled()
    stats = await db.get_notes_stats()
    
    if mode == "name":
        mode_title = "По имени (Классика)"
        mode_expl = "Санта видит имя подопечного в сообщении и карточке."
    elif mode == "gender":
        mode_title = "По полу (Парню / Девушке)"
        mode_expl = "Санта видит только пол подопечного («парню» или «девушке») и его код подарка."
    else:
        mode_title = "Строгий код подарка"
        mode_expl = "Имя и пол полностью скрыты. Санта видит только уникальный код подопечного (например, #48291)."
        
    filter_status = "Включен" if is_filter else "Выключен"
    filter_icon = E_CHECK if is_filter else E_CROSS
    
    mod_status = "Включена" if is_mod else "Выключена"
    mod_icon = E_CHECK if is_mod else E_CROSS
    
    chat_status = "Включен" if is_chat else "Выключен"
    chat_icon = E_CHECK if is_chat else E_CROSS
    
    text = (
        f"{E_LOCK} <b>Центр приватности и анонимного чата</b>\n"
        f"<blockquote><i>Управление видимостью участников, фильтрацией сообщений и анонимным общением</i></blockquote>\n\n"
        f"<b>1. Режим раскрытия подопечного:</b>\n"
        f"• Текущий: <b>{mode_title}</b>\n"
        f"• <i>{mode_expl}</i>\n\n"
        f"<b>2. Автофильтр деанонимизации:</b> {filter_icon} <b>{filter_status}</b>\n"
        f"• <i>Блокирует попытки раскрыть личность через вопросы (проверки на имя, пол, контакты, ссылки).</i>\n\n"
        f"<b>3. Премодерация записок:</b> {mod_icon} <b>{mod_status}</b>\n"
        f"• <i>Каждый вопрос подопечному или ответ Санте сначала отправляется администраторам на проверку.</i>\n\n"
        f"<b>4. Анонимный чат «Санта — Подопечный»:</b> {chat_icon} <b>{chat_status}</b>\n"
        f"• <i>Позволяет участникам уточнять детали подарка через бота без раскрытия своей личности.</i>\n\n"
        f"{E_STATS} <b>Активность записок:</b>\n"
        f"<blockquote>• Всего отправлено: <b>{stats['sent']}</b>\n"
        f"• Одобрено админом: <b>{stats['approved']}</b>\n"
        f"• Отклонено: <b>{stats['rejected']}</b></blockquote>\n\n"
        f"{E_INFO} <i>Нажимайте на кнопки ниже для мгновенного переключения настроек:</i>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_anonymity_keyboard(
            anonymity_mode=mode,
            filter_enabled=is_filter,
            moderation_enabled=is_mod,
            chat_enabled=is_chat
        ),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_anon_mode_cycle")
async def admin_anon_mode_cycle_handler(callback: CallbackQuery, state: FSMContext):
    """Переключение режима раскрытия подопечного"""
    new_mode = await db.cycle_anonymity_mode()
    mode_titles = {
        "code": "Строгий код подарка",
        "name": "По имени (Классический)",
        "gender": "По полу (Парню/Девушке)"
    }
    await callback.answer(f"Режим изменен: {mode_titles.get(new_mode, new_mode)}!", show_alert=True)
    await admin_anonymity_menu(callback, state)

@admin_router.callback_query(F.data == "admin_toggle_filter")
async def admin_toggle_filter_handler(callback: CallbackQuery, state: FSMContext):
    """Переключение автофильтра стоп-слов"""
    new_val = await db.toggle_filter()
    status_str = "ВКЛЮЧЕН" if new_val else "ВЫКЛЮЧЕН"
    await callback.answer(f"Автофильтр деанонимизации: {status_str}!", show_alert=True)
    await admin_anonymity_menu(callback, state)

@admin_router.callback_query(F.data == "admin_toggle_chat")
async def admin_toggle_chat_handler(callback: CallbackQuery, state: FSMContext):
    """Переключение работы анонимного чата"""
    new_val = await db.toggle_chat()
    status_str = "ВКЛЮЧЕН" if new_val else "ВЫКЛЮЧЕН"
    await callback.answer(f"Анонимный чат: {status_str}!", show_alert=True)
    await admin_anonymity_menu(callback, state)

@admin_router.callback_query(F.data == "admin_toggle_moderation")
async def admin_toggle_moderation_handler(callback: CallbackQuery, state: FSMContext):
    """Переключение премодерации записок"""
    new_val = await db.toggle_moderation()
    status_str = "ВКЛЮЧЕНА" if new_val else "ВЫКЛЮЧЕНА"
    await callback.answer(f"Премодерация записок: {status_str}!", show_alert=True)
    await admin_anonymity_menu(callback, state)

@admin_router.callback_query(F.data == "admin_set_deadline")
async def admin_set_deadline_menu(callback: CallbackQuery, state: FSMContext):
    """Установка дедлайна регистрации"""
    current_deadline = await db.get_registration_deadline()
    current_year = datetime.datetime.now().year
    await callback.message.edit_text(
        f"{E_CALENDAR} <b>Изменение дедлайна регистрации</b>\n\n"
        f"Текущий дедлайн: <b>{current_deadline.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
        f"Введите новую дату в формате ДД.ММ.ГГГГ (например, 25.12.{current_year}):",
        reply_markup=get_back_keyboard("admin_settings"),
        parse_mode="HTML"
    )
    await state.set_state(AdminSetDeadline.entering_date)
    await callback.answer()

@admin_router.message(AdminSetDeadline.entering_date)
async def admin_set_deadline_date(message: Message, state: FSMContext):
    """Обработка ввода даты дедлайна"""
    date_str = message.text.strip()
    try:
        day, month, year = map(int, date_str.split('.'))
        date = datetime.datetime(year, month, day)
        await state.update_data(date=date)
        await message.answer(
            f"{E_CALENDAR} Дата сохранена: <b>{date.strftime('%d.%m.%Y')}</b>\n\n"
            f"Теперь введите время в формате ЧЧ:ММ (например, 23:59):",
            reply_markup=get_back_keyboard("admin_set_deadline"),
            parse_mode="HTML"
        )
        await state.set_state(AdminSetDeadline.entering_time)
    except ValueError:
        await message.answer(f"{E_CROSS} Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ", parse_mode="HTML")

@admin_router.message(AdminSetDeadline.entering_time)
async def admin_set_deadline_time(message: Message, state: FSMContext):
    """Обработка ввода времени дедлайна"""
    time_str = message.text.strip()
    try:
        state_data = await state.get_data()
        date = state_data["date"]
        hour, minute = map(int, time_str.split(':'))
        deadline = datetime.datetime(date.year, date.month, date.day, hour, minute)
        
        if deadline < datetime.datetime.now():
            await message.answer(f"{E_CROSS} Дедлайн должен быть в будущем!", parse_mode="HTML")
            return
        
        await db.set_registration_deadline(deadline)
        await message.answer(
            f"{E_CHECK} <b>Дедлайн успешно изменен!</b>\n\n{E_CALENDAR} Новый дедлайн: <b>{deadline.strftime('%d.%m.%Y %H:%M')}</b>",
            parse_mode="HTML"
        )
        await state.clear()
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Назад", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_settings")
        await message.answer("Выберите действие:", reply_markup=keyboard.as_markup())
    except ValueError:
        await message.answer(f"{E_CROSS} Неверный формат времени. Введите время в формате ЧЧ:ММ", parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_distribution_menu")
async def admin_distribution_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления распределением подарков"""
    await state.clear()
    distribution_status = await db.get_distribution_status()
    count = await db.get_participants_count()
    total_participants = await db.get_total_participants()
    is_distributed = await db.is_distribution_done()
    is_revealed = await db.is_reveal_done()
    
    reveal_status_str = "Да" if is_revealed else "Ожидает финала"
    text = (
        f"{E_DICE} <b>Управление распределением</b>\n\n"
        f"{E_USERS} Зарегистрировано: <b>{count}/{total_participants}</b> участников\n"
        f"{E_GIFT} Статус: <i>{distribution_status}</i>\n"
        f"• Финал игры (раскрытие): <b>{reveal_status_str}</b>\n\n"
        f"Выберите действие:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_distribution_keyboard(is_distributed=is_distributed, is_revealed=is_revealed), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_distribute_confirm")
async def admin_distribute_confirm(callback: CallbackQuery):
    """Подтверждение автоматического распределения"""
    can_distribute, message_text = await db.can_perform_auto_distribution()
    if not can_distribute:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Назад", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_distribution_menu")
        await callback.message.edit_text(message_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
        await callback.answer()
        return

    count = await db.get_participants_count()
    total_participants = await db.get_total_participants()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Запустить распределение", icon_custom_emoji_id=emoji_id("party"), callback_data="admin_distribute")
    keyboard.button(text="Отмена", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_distribution_menu")
    keyboard.adjust(1)
    
    text = (
        f"{E_WARNING} <b>Подтверждение распределения</b>\n\n"
        f"{E_USERS} Будут распределены: <b>{count} из {total_participants}</b> участников.\n\n"
        f"После распределения каждый участник мгновенно получит уведомление со своим подопечным!\n\n"
        f"Вы действительно хотите запустить распределение прямо сейчас?"
    )
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_distribution_status")
async def admin_distribution_status(callback: CallbackQuery):
    """Детальный статус распределения"""
    distribution_status = await db.get_distribution_status()
    users = await db.get_all_users()
    is_done = await db.is_distribution_done()
    remaining_givers, remaining_receivers = await db.get_remaining_users_for_distribution()
    
    text = (
        f"{E_STATS} <b>Детальный статус распределения</b>\n\n"
        f"• Текущее состояние: <i>{distribution_status}</i>\n"
        f"• Зарегистрировано участников: <b>{len(users)}</b>\n"
        f"• Распределение завершено: {'<b>Да</b>' if is_done else '<b>Нет</b>'}\n"
        f"• Осталось назначить дарителей: <b>{len(remaining_givers)}</b>\n"
        f"• Осталось получателей без подарка: <b>{len(remaining_receivers)}</b>"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_distribution_menu")
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_broadcasts_menu")
async def admin_broadcasts_menu(callback: CallbackQuery, state: FSMContext):
    """Меню рассылок и уведомлений"""
    await state.clear()
    allowed_users = await db.get_allowed_users()
    registered_count = await db.get_participants_count()
    unregistered_count = len(allowed_users) - registered_count
    
    text = (
        f"{E_MEGAPHONE} <b>Центр рассылок и уведомлений</b>\n\n"
        f"• Зарегистрированных участников: <b>{registered_count}</b>\n"
        f"• Всего в списке доступа: <b>{len(allowed_users)}</b>\n"
        f"• Еще не зарегистрировались: <b>{max(0, unregistered_count)}</b>\n\n"
        f"Выберите тип сообщения или рассылки:"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_broadcasts_keyboard(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_distribute")
async def admin_distribute(callback: CallbackQuery, bot: Bot):
    """Запуск автоматического распределения"""
    can_distribute, message_text = await db.can_perform_auto_distribution()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_distribution_menu")
    
    if not can_distribute:
        await callback.message.edit_text(message_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
        await callback.answer()
        return
    
    count = await db.get_participants_count()
    total_participants = await db.get_total_participants()
    if count < total_participants:
        await callback.message.edit_text(
            f"{E_CROSS} <b>Недостаточно участников!</b>\nЗарегистрировано: <b>{count}/{total_participants}</b>",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    success = await db.make_distribution()
    if success:
        await callback.message.edit_text(
            f"{E_CHECK} <b>Автоматическое распределение выполнено успешно!</b>\nВсе участники получат информацию о том, кому дарить.",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await notify_all_participants(bot, db)
    else:
        await callback.message.edit_text(
            f"{E_WARNING} <b>Автоматическое распределение не выполнено.</b> Проверьте количество участников.",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_manual_distribute")
async def admin_manual_distribute_menu(callback: CallbackQuery, state: FSMContext):
    """Меню ручного распределения"""
    if await db.is_distribution_done():
        await callback.message.edit_text(f"{E_CHECK} Все участники уже распределены!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
        await callback.answer()
        return
    
    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text(f"{E_CROSS} Нет зарегистрированных пользователей", reply_markup=get_back_keyboard("admin_panel"), parse_mode="HTML")
        await callback.answer()
        return
    
    available_givers = {uid: u for uid, u in users.items() if not u.get('gift_to_user_id')}
    remaining_givers, remaining_receivers = await db.get_remaining_users_for_distribution()
    
    if not available_givers:
        if remaining_receivers:
            await callback.message.edit_text(
                f"{E_WARNING} Все пользователи уже являются дарителями, но есть <b>{len(remaining_receivers)}</b> получателей без дарителей.\n"
                f"Хотите выполнить авто-распределение для оставшихся?",
                reply_markup=get_distribution_confirmation_keyboard(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(f"{E_CHECK} Все пользователи уже распределены!", reply_markup=get_admin_keyboard(), parse_mode="HTML")
        await callback.answer()
        return
    
    status_text = (
        f"{E_PUZZLE} <b>Ручное распределение</b>\n\n"
        f"{E_STATS} <b>Статистика:</b>\n"
        f"• Всего участников: <b>{len(users)}</b>\n"
        f"• Осталось дарителей: <b>{len(available_givers)}</b>\n"
        f"• Осталось получателей: <b>{len(remaining_receivers)}</b>\n\n"
        "Выберите дарителя (кто будет дарить подарок):"
    )
    await callback.message.edit_text(status_text, reply_markup=get_users_keyboard(available_givers, "giver_"), parse_mode="HTML")
    await state.set_state(AdminManualDistribution.selecting_giver)
    await state.update_data(users=users)
    await callback.answer()

@admin_router.callback_query(AdminManualDistribution.selecting_giver, F.data.startswith("giver_"))
async def admin_manual_distribute_select_giver(callback: CallbackQuery, state: FSMContext):
    """Выбор дарителя для ручного распределения"""
    giver_id_str = callback.data.replace("giver_", "")
    giver_id = int(giver_id_str)
    await state.update_data(giver_id=giver_id)
    
    state_data = await state.get_data()
    users = state_data.get("users", {})
    
    available_receivers = {}
    for uid, udata in users.items():
        if uid == giver_id_str:
            continue
        is_receiving = any(other.get('gift_to_user_id') == int(uid) for other in users.values())
        if not is_receiving:
            available_receivers[uid] = udata
    
    giver_data = users.get(giver_id_str, {})
    giver_name = giver_data.get("display_name") or giver_data.get("username", f"ID {giver_id}")
    
    if not available_receivers:
        await callback.message.edit_text(
            f"{E_CROSS} Нет доступных получателей для <b>{giver_name}</b>.",
            reply_markup=get_distribution_confirmation_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"{E_PUZZLE} <b>Ручное распределение</b>\n\nДаритель: <b>{giver_name}</b> (<code>ID: {giver_id}</code>)\n\nВыберите получателя:",
        reply_markup=get_users_keyboard(available_receivers, "receiver_"),
        parse_mode="HTML"
    )
    await state.set_state(AdminManualDistribution.selecting_receiver)
    await callback.answer()

@admin_router.callback_query(F.data == "confirm_mixed_distribution")
async def confirm_mixed_distribution(callback: CallbackQuery, bot: Bot):
    """Подтверждение смешанного распределения"""
    success = await db.make_distribution()
    if success:
        await callback.message.edit_text(
            f"{E_CHECK} <b>Смешанное распределение выполнено успешно!</b>\nОставшиеся участники распределены автоматически.",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
        await notify_all_participants(bot, db)
    else:
        await callback.message.edit_text(
            f"{E_WARNING} Не удалось выполнить автоматическое распределение для оставшихся.",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()

@admin_router.callback_query(AdminManualDistribution.selecting_receiver, F.data.startswith("receiver_"))
async def admin_manual_distribute_select_receiver(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Выбор получателя и завершение ручного распределения"""
    receiver_id_str = callback.data.replace("receiver_", "")
    receiver_id = int(receiver_id_str)
    
    state_data = await state.get_data()
    giver_id = state_data.get("giver_id")
    users = state_data.get("users", {})
    
    giver_data = users.get(str(giver_id), {})
    receiver_data = users.get(receiver_id_str, {})
    
    giver_name = giver_data.get("display_name") or giver_data.get("username", f"ID {giver_id}")
    receiver_name = receiver_data.get("display_name") or receiver_data.get("username", f"ID {receiver_id}")
    
    success = await db.manual_distribution(giver_id, receiver_id)
    if success:
        if await db.is_distribution_done():
            await callback.message.edit_text(
                f"{E_CHECK} <b>Ручное распределение выполнено!</b>\n"
                f"• Даритель: <b>{giver_name}</b> → Получатель: <b>{receiver_name}</b>\n\n"
                f"{E_PARTY} <b>Все участники распределены!</b>",
                reply_markup=get_admin_keyboard(),
                parse_mode="HTML"
            )
            await notify_all_participants(bot, db)
        else:
            remaining_givers, remaining_receivers = await db.get_remaining_users_for_distribution()
            status_text = (
                f"{E_CHECK} <b>Распределение сохранено!</b>\n"
                f"• <b>{giver_name}</b> → <b>{receiver_name}</b>\n\n"
                f"{E_STATS} Осталось: Дарителей <b>{len(remaining_givers)}</b>, Получателей <b>{len(remaining_receivers)}</b>"
            )
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="Продолжить ручное распределение", icon_custom_emoji_id=emoji_id("puzzle"), callback_data="admin_manual_distribute")
            if len(remaining_givers) > 1:
                keyboard.button(text="Распределить оставшихся автоматически", icon_custom_emoji_id=emoji_id("dice"), callback_data="admin_distribute")
            keyboard.button(text="В админ-панель", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_panel")
            keyboard.adjust(1)
            await callback.message.edit_text(status_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
        
        # Отправляем уведомление дарителю (если еще не все распределены, иначе notify_all_participants уже уведомил всех)
        if not await db.is_distribution_done():
            receiver_wish = html.escape(receiver_data.get('wish', 'не указано'), quote=False)
            receiver_links = format_wish_links(receiver_data.get('wish_link', ''))
            mode = await db.get_anonymity_mode()
            rec_info = format_recipient_info_for_santa(receiver_data, mode)
            
            message = (
                f"{E_GIFT_STAR} <b>Ручное распределение Тайного Санты!</b>\n\n"
                f"{rec_info}"
                f"• Желание получателя: <i>«{receiver_wish}»</i>\n"
            )
            if receiver_links and receiver_links != "Нет ссылки":
                message += f"\n{E_LINK} Ссылки на подарки:\n{receiver_links}\n"
            message += f"\n{E_MONEY} Бюджет: до <b>{GIFT_BUDGET} рублей</b>\n\n{E_SPARKLES} С наступающим Новым Годом!"
            
            notif_kb = InlineKeyboardBuilder()
            notif_kb.button(text="Спросить подопечного анонимно", callback_data="ask_receiver", icon_custom_emoji_id=emoji_id("new_message"))
            notif_kb.button(text="Моя анкета", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
            notif_kb.adjust(1)
            
            await send_message_safe(bot, giver_id, message, reply_markup=notif_kb.as_markup(), parse_mode="HTML")
    else:
        await callback.message.edit_text(f"{E_CROSS} Ошибка ручного распределения", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    
    await state.clear()
    await callback.answer()

@admin_router.callback_query(F.data == "admin_reset_distribution")
async def admin_reset_distribution(callback: CallbackQuery):
    """Сброс распределения"""
    success = await db.reset_distribution()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Назад", icon_custom_emoji_id=emoji_id("back"), callback_data="admin_distribution_menu")
    
    if success:
        await callback.message.edit_text(f"{E_CHECK} Распределение успешно сброшено!", reply_markup=keyboard.as_markup(), parse_mode="HTML")
    else:
        await callback.message.edit_text(f"{E_CROSS} Не удалось сбросить распределение", reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

async def prepare_and_show_broadcast_preview(
    message: Message,
    state: FSMContext,
    recipient_ids: list,
    target_desc: str,
    header: str,
    cancel_callback: str,
    back_state
):
    """Формирует и отправляет карточку предпросмотра рассылки администратору"""
    if message.photo:
        raw_html = message.html_caption or ""
        photo_id = message.photo[-1].file_id
    else:
        raw_html = message.html_text or ""
        photo_id = None

    if not raw_html and not photo_id:
        await message.answer(
            f"{E_WARNING} Пожалуйста, отправьте текст сообщения или фотографию с описанием.",
            parse_mode="HTML"
        )
        return

    # Проверка лимитов длины Telegram
    if photo_id and len(raw_html) > 1024:
        await message.answer(
            f"{E_CROSS} Подпись к фотографии слишком длинная ({len(raw_html)}/1024 симв.). Пожалуйста, сократите текст.",
            parse_mode="HTML"
        )
        return
    elif not photo_id and len(raw_html) > 4000:
        await message.answer(
            f"{E_CROSS} Сообщение слишком длинное ({len(raw_html)}/4000 симв.). Пожалуйста, сократите текст.",
            parse_mode="HTML"
        )
        return

    rendered_body = render_text_with_custom_emojis(raw_html)
    final_message_text = f"{header}\n\n{rendered_body}" if header else rendered_body

    await state.update_data(
        broadcast_recipient_ids=recipient_ids,
        broadcast_final_text=final_message_text,
        broadcast_photo_id=photo_id,
        broadcast_target_desc=target_desc,
        broadcast_cancel_callback=cancel_callback,
        broadcast_back_state=back_state
    )

    caption_preview = (
        f"{E_SEARCH} <b>Предпросмотр сообщения для получателей:</b>\n"
        f"<blockquote><b>Кому:</b> {target_desc} ({len(recipient_ids)} чел.)</blockquote>\n\n"
        f"{final_message_text}"
    )

    preview_kb = get_broadcast_preview_keyboard(cancel_callback)

    if photo_id:
        if len(caption_preview) <= 1024:
            await message.answer_photo(
                photo=photo_id,
                caption=caption_preview,
                reply_markup=preview_kb,
                parse_mode="HTML"
            )
        else:
            await message.answer_photo(
                photo=photo_id,
                caption=final_message_text[:1024],
                parse_mode="HTML"
            )
            await message.answer(
                f"{E_SEARCH} <b>Предпросмотр:</b>\n<blockquote><b>Кому:</b> {target_desc} ({len(recipient_ids)} чел.)</blockquote>",
                reply_markup=preview_kb,
                parse_mode="HTML"
            )
    else:
        await message.answer(
            caption_preview,
            reply_markup=preview_kb,
            parse_mode="HTML"
        )

@admin_router.callback_query(F.data == "admin_notify_all")
async def admin_notify_all_menu(callback: CallbackQuery, state: FSMContext):
    """Уведомление зарегистрированных участников"""
    users = await db.get_all_users()
    if not users:
        await callback.answer("Нет зарегистрированных участников", show_alert=True)
        return
        
    await callback.message.edit_text(
        f"{E_MEGAPHONE} <b>Рассылка зарегистрированным участникам</b>\n\n"
        f"Получателей: <b>{len(users)}</b> чел.\n\n"
        f"Отправьте текст сообщения или <b>фотографию с подписью</b>:\n\n"
        f"<blockquote>• Премиум эмодзи: выберите в клавиатуре или укажите шорткод (например, <code>:gift:</code>, <code>:party:</code>, <code>:star:</code>, <code>:bell:</code>)\n"
        f"• Форматирование: жирный, курсив, цитаты, спойлеры\n"
        f"• Перед отправкой будет доступен предпросмотр</blockquote>",
        reply_markup=get_back_keyboard("admin_broadcasts_menu"),
        parse_mode="HTML"
    )
    await state.set_state(AdminNotifyAll.entering_message)
    await callback.answer()

@admin_router.message(AdminNotifyAll.entering_message)
async def admin_notify_all_process(message: Message, state: FSMContext):
    """Предпросмотр сообщения для зарегистрированных участников"""
    users = await db.get_all_users()
    if not users:
        await message.answer(f"{E_CROSS} Нет зарегистрированных участников", parse_mode="HTML")
        await state.clear()
        return
    
    recipient_ids = [int(uid) for uid in users.keys()]
    await prepare_and_show_broadcast_preview(
        message=message,
        state=state,
        recipient_ids=recipient_ids,
        target_desc="Все зарегистрированные участники",
        header=f"{E_MEGAPHONE} <b>Сообщение от организаторов Тайного Санты:</b>",
        cancel_callback="admin_broadcasts_menu",
        back_state=AdminNotifyAll.entering_message
    )
    await state.set_state(AdminNotifyAll.confirming)

@admin_router.callback_query(F.data == "admin_notify_all_users")
async def admin_notify_all_users_menu(callback: CallbackQuery, state: FSMContext):
    """Уведомление всех пользователей из списка доступа"""
    allowed_users = await db.get_allowed_users()
    if not allowed_users:
        await callback.answer("Нет пользователей в списке доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"{E_BROADCAST} <b>Рассылка по списку доступа</b>\n\n"
        f"Получателей: <b>{len(allowed_users)}</b> чел. (включая незарегистрированных)\n\n"
        f"Отправьте текст сообщения или <b>фотографию с подписью</b>:\n\n"
        f"<blockquote>• Премиум эмодзи: выберите в клавиатуре или укажите шорткод (например, <code>:gift:</code>, <code>:party:</code>, <code>:star:</code>, <code>:bell:</code>)\n"
        f"• Форматирование: жирный, курсив, цитаты, спойлеры\n"
        f"• Перед отправкой будет доступен предпросмотр</blockquote>",
        reply_markup=get_back_keyboard("admin_broadcasts_menu"),
        parse_mode="HTML"
    )
    await state.set_state(AdminNotifyAllUsers.entering_message)
    await callback.answer()

@admin_router.message(AdminNotifyAllUsers.entering_message)
async def admin_notify_all_users_process(message: Message, state: FSMContext):
    """Предпросмотр сообщения для всех пользователей из списка доступа"""
    allowed_users = await db.get_allowed_users()
    if not allowed_users:
        await message.answer(f"{E_CROSS} Нет пользователей в списке доступа", parse_mode="HTML")
        await state.clear()
        return
    
    await prepare_and_show_broadcast_preview(
        message=message,
        state=state,
        recipient_ids=allowed_users,
        target_desc="Все пользователи из списка доступа",
        header=f"{E_BROADCAST} <b>Сообщение от организаторов Тайного Санты:</b>",
        cancel_callback="admin_broadcasts_menu",
        back_state=AdminNotifyAllUsers.entering_message
    )
    await state.set_state(AdminNotifyAllUsers.confirming)

@admin_router.callback_query(F.data == "admin_notify_selected")
async def admin_notify_selected_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора пользователей для рассылки"""
    users = await db.get_all_users()
    allowed_users = await db.get_allowed_users()
    
    for uid in allowed_users:
        if str(uid) not in users:
            users[str(uid)] = {"username": f"ID {uid}", "display_name": "", "registered": False}
    
    await state.update_data(selected_users=[], users=users)
    await callback.message.edit_text(
        f"{E_MESSAGE} <b>Выберите пользователей для рассылки:</b>\n\n"
        f"Нажимайте на кнопки участников, чтобы отметить получателей:",
        reply_markup=get_multi_select_keyboard(users, [], "admin_broadcasts_menu"),
        parse_mode="HTML"
    )
    await state.set_state(AdminNotifySelected.selecting_users)
    await callback.answer()

@admin_router.callback_query(AdminNotifySelected.selecting_users, F.data.startswith("select_"))
async def admin_notify_selected_toggle(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора пользователя"""
    user_id_str = callback.data.replace("select_", "")
    state_data = await state.get_data()
    selected_users = state_data.get("selected_users", [])
    users = state_data.get("users", {})
    
    if user_id_str in selected_users:
        selected_users.remove(user_id_str)
    else:
        selected_users.append(user_id_str)
    
    await state.update_data(selected_users=selected_users)
    await callback.message.edit_text(
        f"{E_MESSAGE} <b>Выберите пользователей для рассылки:</b>\n\n"
        f"{E_CHECK} Отмечено получателей: <b>{len(selected_users)}</b> чел.",
        reply_markup=get_multi_select_keyboard(users, selected_users, "admin_broadcasts_menu"),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(AdminNotifySelected.selecting_users, F.data == "continue_with_selected")
async def admin_notify_selected_continue(callback: CallbackQuery, state: FSMContext):
    """Ввод сообщения для выбранных пользователей"""
    state_data = await state.get_data()
    selected_users = state_data.get("selected_users", [])
    if not selected_users:
        await callback.answer("Вы не выбрали ни одного пользователя", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"{E_MESSAGE} <b>Рассылка выбранным участникам</b>\n\n"
        f"Получателей: <b>{len(selected_users)}</b> чел.\n\n"
        f"Отправьте текст сообщения или <b>фотографию с подписью</b>:\n\n"
        f"<blockquote>• Премиум эмодзи: выберите в клавиатуре или укажите шорткод (например, <code>:gift:</code>, <code>:party:</code>, <code>:star:</code>, <code>:bell:</code>)\n"
        f"• Форматирование: жирный, курсив, цитаты, спойлеры\n"
        f"• Перед отправкой будет доступен предпросмотр</blockquote>",
        reply_markup=get_back_keyboard("admin_notify_selected"),
        parse_mode="HTML"
    )
    await state.set_state(AdminNotifySelected.entering_message)
    await callback.answer()

@admin_router.message(AdminNotifySelected.entering_message)
async def admin_notify_selected_process(message: Message, state: FSMContext):
    """Предпросмотр сообщения для выбранных пользователей"""
    state_data = await state.get_data()
    selected_users = state_data.get("selected_users", [])
    if not selected_users:
        await message.answer(f"{E_CROSS} Список получателей пуст", parse_mode="HTML")
        await state.clear()
        return
    
    recipient_ids = [int(uid) for uid in selected_users]
    await prepare_and_show_broadcast_preview(
        message=message,
        state=state,
        recipient_ids=recipient_ids,
        target_desc="Выбранные участники",
        header=f"{E_MESSAGE} <b>Сообщение от организаторов Тайного Санты:</b>",
        cancel_callback="admin_notify_selected",
        back_state=AdminNotifySelected.entering_message
    )
    await state.set_state(AdminNotifySelected.confirming)

@admin_router.callback_query(F.data == "broadcast_confirm_send")
async def broadcast_confirm_send_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение и запуск отправки рассылки / личного сообщения"""
    state_data = await state.get_data()
    recipient_ids = state_data.get("broadcast_recipient_ids", [])
    final_text = state_data.get("broadcast_final_text", "")
    photo_id = state_data.get("broadcast_photo_id")
    cancel_callback = state_data.get("broadcast_cancel_callback", "admin_broadcasts_menu")

    if not recipient_ids or (not final_text and not photo_id):
        await callback.answer("Данные рассылки устарели или не найдены", show_alert=True)
        await state.clear()
        return

    await callback.answer()

    status_msg = await callback.message.answer(
        f"{E_HOURGLASS} <b>Выполняется отправка сообщений...</b>\n\n"
        f"Получателей: <b>{len(recipient_ids)}</b> чел. Пожалуйста, подождите.",
        parse_mode="HTML"
    )

    success_count = 0
    fail_count = 0
    for uid in recipient_ids:
        success, _ = await send_message_safe(
            bot,
            uid,
            text=final_text,
            photo=photo_id,
            parse_mode="HTML"
        )
        if success:
            success_count += 1
        else:
            fail_count += 1
        await asyncio.sleep(0.05)

    await state.clear()

    keyboard = InlineKeyboardBuilder()
    if cancel_callback.startswith("admin_user_view_"):
        uid = cancel_callback.replace("admin_user_view_", "")
        keyboard.button(text="К карточке участника", callback_data=f"admin_user_view_{uid}", icon_custom_emoji_id=emoji_id("user"))
        keyboard.button(text="Список участников", callback_data="admin_users_list", icon_custom_emoji_id=emoji_id("users"))
        keyboard.adjust(1)
    else:
        keyboard.button(text="В центр рассылок", callback_data="admin_broadcasts_menu", icon_custom_emoji_id=emoji_id("back"))

    await status_msg.edit_text(
        f"{E_CHECK} <b>Рассылка успешно завершена!</b>\n\n"
        f"<blockquote>• Успешно доставлено: <b>{success_count}</b>\n"
        f"• Ошибок / заблокировали бота: <b>{fail_count}</b>\n"
        f"• Всего получателей: <b>{len(recipient_ids)}</b></blockquote>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data == "broadcast_edit_text")
async def broadcast_edit_text_handler(callback: CallbackQuery, state: FSMContext):
    """Возврат к редактированию текста/фото рассылки"""
    state_data = await state.get_data()
    back_state = state_data.get("broadcast_back_state")
    cancel_callback = state_data.get("broadcast_cancel_callback", "admin_broadcasts_menu")
    target_desc = state_data.get("broadcast_target_desc", "")

    if back_state:
        await state.set_state(back_state)

    await callback.message.answer(
        f"{E_EDIT} <b>Редактирование сообщения</b>\n\n"
        f"Кому: <b>{target_desc}</b>\n\n"
        f"Отправьте новый текст сообщения или фотографию с подписью:",
        reply_markup=get_back_keyboard(cancel_callback),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_remind")
async def admin_remind(callback: CallbackQuery, bot: Bot):
    """Ручная отправка напоминаний незарегистрированным пользователям"""
    await callback.message.edit_text(f"{E_CLOCK} Отправка напоминаний незарегистрированным пользователям...", parse_mode="HTML")
    
    allowed_users = await db.get_allowed_users()
    total_participants = await db.get_total_participants()
    unregistered = await db.get_unregistered_users()
    now = datetime.datetime.now()
    registration_deadline = await db.get_registration_deadline()
    
    if now > registration_deadline:
        await callback.message.edit_text(f"{E_CROSS} Регистрация уже закрыта!", reply_markup=get_admin_broadcasts_keyboard(), parse_mode="HTML")
        await callback.answer()
        return
    
    if not unregistered:
        count = await db.get_participants_count()
        if count >= total_participants:
            msg = f"{E_PARTY} Все <b>{total_participants}</b> участников уже успешно зарегистрированы!"
        else:
            missing_count = total_participants - len(allowed_users)
            msg = (
                f"{E_INFO} Все пользователи из текущего списка доступа ({len(allowed_users)} чел.) уже зарегистрированы!\n\n"
                f"{E_WARNING} Боту некому отправлять напоминания, так как остальные <b>{missing_count}</b> участников ещё не добавлены в список доступа.\n\n"
                f"Добавьте их через раздел <b>«Управление участниками»</b> или попросите их зайти в бота и нажать <i>«Подать заявку на участие»</i>."
            )
        await callback.message.edit_text(msg, reply_markup=get_admin_broadcasts_keyboard(), parse_mode="HTML")
        await callback.answer()
        return
    
    days_left = (registration_deadline - now).days
    reminders_sent = 0
    for uid in unregistered:
        if days_left == 1:
            msg = (
                f"{E_CLOCK} <b>СРОЧНОЕ НАПОМИНАНИЕ!</b>\n\n"
                f"До закрытия регистрации в Тайном Санте остался <b>1 ДЕНЬ</b>!\n"
                f"Нажмите /start для регистрации."
            )
        elif days_left <= 3:
            msg = (
                f"{E_BELL} <b>Напоминание о Тайном Санте!</b>\n\n"
                f"Осталось <b>{days_left} дня</b>! Нажмите /start для регистрации."
            )
        else:
            msg = (
                f"{E_BELL} <b>Напоминание о Тайном Санте!</b>\n\n"
                f"Не забудьте зарегистрироваться до <b>{registration_deadline.strftime('%d.%m.%Y %H:%M')}</b>\n"
                f"Нажмите /start."
            )
        
        success, _ = await send_message_safe(bot, uid, msg, parse_mode="HTML")
        if success:
            await db.update_last_reminder(uid)
            reminders_sent += 1
        await asyncio.sleep(0.05)
    
    await callback.message.edit_text(
        f"{E_CHECK} <b>Напоминания отправлены!</b>\nОтправлено: <b>{reminders_sent}/{len(unregistered)}</b>",
        reply_markup=get_admin_broadcasts_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

# -------------------------------------------------------------
# Премодерация анонимных записок администраторами
# -------------------------------------------------------------

@admin_router.callback_query(F.data.startswith("mod_appr_"))
async def admin_approve_note(callback: CallbackQuery, bot: Bot):
    """Одобрение анонимной записки администратором"""
    note_id = callback.data.replace("mod_appr_", "")
    note = await db.pop_pending_note(note_id)
    
    if not note:
        await callback.answer("Эта записка уже была обработана другим администратором.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    
    sender_id = note["sender_id"]
    target_id = note["target_id"]
    note_type = note["note_type"]
    text_content = note["text"]
    escaped_text = html.escape(text_content, quote=False)
    
    admin_uname = callback.from_user.username
    admin_signature = f"@{admin_uname}" if admin_uname else callback.from_user.first_name
    
    if note_type == "question":
        receiver_text = (
            f"{E_GIFT} <b>Вам пришла анонимная записка от вашего Тайного Санты!</b>\n\n"
            f"<blockquote>«{escaped_text}»</blockquote>\n\n"
            f"{E_SPARKLES} <i>Вы можете ответить Санте анонимно, нажав кнопку ниже:</i>"
        )
        receiver_kb = InlineKeyboardBuilder()
        receiver_kb.button(
            text="Ответить Санте",
            callback_data=f"reply_santa_{sender_id}",
            icon_custom_emoji_id=emoji_id("new_message")
        )
        receiver_kb.adjust(1)
        
        success, _ = await send_message_safe(bot, target_id, receiver_text, reply_markup=receiver_kb.as_markup(), parse_mode="HTML")
        if success:
            await send_message_safe(
                bot, sender_id,
                f"{E_CHECK} <b>Ваша записка проверена администратором и доставлена подопечному!</b>\n\n"
                f"{E_HOURGLASS} Как только он ответит, вам придёт уведомление.",
                parse_mode="HTML"
            )
        else:
            await send_message_safe(
                bot, sender_id,
                f"{E_WARNING} Записка была одобрена, но её не удалось доставить подопечному (возможно, пользователь заблокировал бота).",
                parse_mode="HTML"
            )
    else:
        santa_text = (
            f"{E_MESSAGE} <b>Ответ от вашего подопечного!</b>\n\n"
            f"<blockquote>«{escaped_text}»</blockquote>\n\n"
            f"{E_SPARKLES} <i>Если хотите уточнить ещё что-то, вы можете задать новый вопрос:</i>"
        )
        santa_kb = InlineKeyboardBuilder()
        santa_kb.button(
            text="Задать ещё вопрос",
            callback_data="ask_receiver",
            icon_custom_emoji_id=emoji_id("new_message")
        )
        santa_kb.button(
            text="Моя анкета",
            callback_data="myinfo",
            icon_custom_emoji_id=emoji_id("gift")
        )
        santa_kb.adjust(1)
        
        success, _ = await send_message_safe(bot, target_id, santa_text, reply_markup=santa_kb.as_markup(), parse_mode="HTML")
        if success:
            await send_message_safe(
                bot, sender_id,
                f"{E_CHECK} <b>Ваш ответ проверен администратором и доставлен вашему Тайному Санте!</b>",
                parse_mode="HTML"
            )
        else:
            await send_message_safe(
                bot, sender_id,
                f"{E_WARNING} Ответ был одобрен, но Санта временно недоступен.",
                parse_mode="HTML"
            )
            
    await db.save_anonymous_note(
        from_user_id=sender_id,
        to_user_id=target_id,
        note_type=note_type,
        text=text_content
    )
    await db.increment_notes_stat("approved")
    
    try:
        new_text = callback.message.html_text + f"\n\n{E_CHECK} <b>Одобрено администратором {admin_signature}</b>"
        await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Записка успешно одобрена и доставлена!")

@admin_router.callback_query(F.data.startswith("mod_rejl_"))
async def admin_reject_note(callback: CallbackQuery, bot: Bot):
    """Отклонение анонимной записки администратором"""
    note_id = callback.data.replace("mod_rejl_", "")
    note = await db.pop_pending_note(note_id)
    
    if not note:
        await callback.answer("Эта записка уже была обработана.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    
    sender_id = note["sender_id"]
    admin_uname = callback.from_user.username
    admin_signature = f"@{admin_uname}" if admin_uname else callback.from_user.first_name
    
    await send_message_safe(
        bot, sender_id,
        f"{E_CROSS} <b>Ваша записка была отклонена администратором.</b>\n\n"
        f"<i>Причина: вопрос нарушает правила анонимности или содержит некорректный текст. "
        f"Пожалуйста, задавайте вопросы только о пожеланиях к подарку (размер, цвет, хобби, аллергия).</i>",
        parse_mode="HTML"
    )
    await db.increment_notes_stat("rejected")
    
    try:
        new_text = callback.message.html_text + f"\n\n{E_CROSS} <b>Отклонено администратором {admin_signature}</b>"
        await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Записка отклонена.")

# -------------------------------------------------------------
# Финал игры — «Раскрытие тайны Санты» (Grand Reveal)
# -------------------------------------------------------------

@admin_router.callback_query(F.data == "admin_reveal_confirm")
async def admin_reveal_confirm(callback: CallbackQuery):
    """Подтверждение финального раскрытия тайн Санты"""
    if not await db.is_distribution_done():
        await callback.answer("Распределение ещё не проведено!", show_alert=True)
        return
    
    if await db.is_reveal_done():
        await callback.answer("Тайна Санты уже была раскрыта ранее!", show_alert=True)
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Да, раскрыть тайну всем!", callback_data="admin_reveal_do", icon_custom_emoji_id=emoji_id("party"))
    keyboard.button(text="Отмена", callback_data="admin_distribution_menu", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    text = (
        f"{E_PARTY} <b>Финал игры: Раскрытие тайн Санты</b>\n\n"
        f"{E_WARNING} <b>Внимание!</b> Это действие завершает интригу игры.\n\n"
        f"Каждый участник получит персональное праздничное сообщение:\n"
        f"• Кто был его Тайным Сантой (имя и фамилия)\n"
        f"• Кому он дарил подарок (имя и фамилия)\n\n"
        f"Вы уверены, что подарки уже вручены и пора раскрыть карты?"
    )
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_reveal_do")
async def admin_reveal_do(callback: CallbackQuery, bot: Bot):
    """Выполнение рассылки раскрытия тайн Санты"""
    if await db.is_reveal_done():
        await callback.answer("Тайна уже раскрыта!", show_alert=True)
        return
    
    await db.set_reveal_done(True)
    pairs = await db.get_distribution_pairs()
    
    santa_map = {}
    receiver_map = {}
    all_users = set()
    
    for p in pairs:
        giver_id = p["giver_id"]
        receiver_id = p["receiver_id"]
        all_users.add(giver_id)
        all_users.add(receiver_id)
        santa_map[receiver_id] = p["giver_name"]
        receiver_map[giver_id] = (p["receiver_name"], p["receiver_key"])
    
    success_count = 0
    fail_count = 0
    
    for uid in all_users:
        santa_name = santa_map.get(uid, "Таинственный Санта")
        receiver_info = receiver_map.get(uid)
        if receiver_info:
            receiver_name, receiver_key = receiver_info
            rec_text = f"• А вы дарили подарок для: <b>{receiver_name}</b> (Код: <code>#{receiver_key}</code>)\n"
        else:
            rec_text = ""
        
        reveal_msg = (
            f"{E_PARTY} <b>ТАЙНА САНТЫ РАСКРЫТА!</b>\n\n"
            f"{E_GIFT} <b>Вашим Тайным Сантой был(а):</b>\n"
            f"{E_CROWN} <b>{santa_name}</b>!\n\n"
            f"{rec_text}\n"
            f"{E_SPARKLES} <i>Надеемся, подарки принесли вам море радости и новогоднего настроения!\n"
            f"Счастливого Нового Года!</i>"
        )
        
        ok, _ = await send_message_safe(bot, uid, reveal_msg, parse_mode="HTML")
        if ok:
            success_count += 1
        else:
            fail_count += 1
        await asyncio.sleep(0.05)
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="В админ-панель", callback_data="admin_panel", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    await callback.message.edit_text(
        f"{E_CHECK} <b>Тайна Санты успешно раскрыта!</b>\n\n"
        f"• Успешно уведомлено: <b>{success_count}</b> участников\n"
        f"• Не доставлено: <b>{fail_count}</b>\n\n"
        f"{E_PARTY} <b>Игра «Тайный Санта» успешно завершена!</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()
