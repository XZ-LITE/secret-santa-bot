import re
import html
import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import GIFT_BUDGET, ADMIN_IDS
from database import db
from states import Registration, ChangeWish, ChangeGender, SetDisplayName
from keyboards import (
    get_start_keyboard,
    get_gender_keyboard,
    get_back_keyboard,
    get_help_keyboard,
    get_wish_link_keyboard
)
from utils import (
    get_main_menu_text,
    is_registration_open,
    format_wish_links,
    validate_wish_link,
    send_message_safe,
    generate_progress_bar
)
from custom_emojis import (
    E_USER, E_USERS, E_GIFT, E_GIFT_STAR, E_GIFT_GIVE, E_CHECK, E_CROSS,
    E_ERASE, E_TRASH, E_HOURGLASS, E_CALENDAR, E_CLOCK, E_MONEY, E_PARTY,
    E_TAG, E_LOCK, E_EDIT, E_REPEAT, E_LINK, E_SPARKLES, E_STATS, E_WARNING,
    E_QUESTION, E_BELL, E_MESSAGE, E_INFO, E_FILE, E_SETTINGS, E_ADD_USER,
    E_SEARCH, emoji_id
)
from services.notifications import notify_admins_registration_complete

user_router = Router(name="user")

@user_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Начало работы с ботом"""
    if not await db.check_access(message.from_user.id):
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Подать заявку на участие", callback_data="request_access", icon_custom_emoji_id=emoji_id("message"))
        await message.answer(
            f"{E_WARNING} <b>Доступ ограничен.</b> Этот бот предназначен только для участников закрытой группы/класса.\n\n"
            "Если вы хотите участвовать в игре «Тайный Санта», нажмите кнопку ниже, чтобы отправить заявку администраторам:",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        return
    
    await state.clear()
    
    is_registered = await db.is_user_registered(message.from_user.id)
    user_data = None
    if is_registered:
        user_data = await db.get_user(message.from_user.id)
        if not user_data.get('display_name'):
            await message.answer(
                f"{E_USER} Пожалуйста, введите ваше имя и фамилию (как вас называть в классе):\n\n"
                "Например: Иванов Иван",
                parse_mode="HTML"
            )
            await state.set_state(SetDisplayName.entering_display_name)
            return
    
    total_participants = await db.get_total_participants()
    registered_count = await db.get_participants_count()
    user_key = user_data.get('key') if user_data else None
    display_name = user_data.get('display_name') if user_data and user_data.get('display_name') else message.from_user.first_name

    await message.answer(
        get_main_menu_text(
            first_name=display_name,
            total_participants=total_participants,
            registered_count=registered_count,
            is_registered=is_registered,
            user_key=user_key
        ),
        reply_markup=get_start_keyboard(message.from_user.id, is_registered=is_registered),
        parse_mode="HTML"
    )

@user_router.callback_query(F.data == "request_access")
async def process_request_access(callback: CallbackQuery, bot: Bot):
    """Обработка подачи заявки на доступ к боту"""
    user_id = callback.from_user.id
    if await db.check_access(user_id):
        await callback.answer("✅ У вас уже есть доступ к боту! Нажмите /start", show_alert=True)
        return
    
    if await db.has_pending_access_request(user_id):
        await callback.answer("⏳ Ваша заявка уже на рассмотрении у администраторов!", show_alert=True)
        return
    
    user_info = {
        "full_name": callback.from_user.full_name,
        "username": callback.from_user.username or "",
        "request_date": datetime.datetime.now().isoformat()
    }
    await db.add_access_request(user_id, user_info)
    
    await callback.message.edit_text(
        f"{E_HOURGLASS} Ваша заявка успешно отправлена администраторам!\n\n"
        "Ожидайте подтверждения. Как только доступ будет одобрен, вам придёт уведомление от бота.",
        parse_mode="HTML"
    )
    await callback.answer("Заявка отправлена!")
    
    user_name = callback.from_user.full_name
    if callback.from_user.username:
        user_name += f" (@{callback.from_user.username})"
    
    admin_text = (
        f"{E_BELL} <b>Новая заявка на участие в Тайном Санте!</b>\n\n"
        f"{E_USER} Пользователь: {user_name}\n"
        f"• Telegram ID: <code>{user_id}</code>\n\n"
        f"Добавить участника в список разрешенных?"
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Одобрить", callback_data=f"approve_user_{user_id}", icon_custom_emoji_id=emoji_id("check"))
    keyboard.button(text="Отклонить", callback_data=f"reject_user_{user_id}", icon_custom_emoji_id=emoji_id("cross"))
    keyboard.adjust(2)
    
    for admin_id in ADMIN_IDS:
        await send_message_safe(bot, admin_id, admin_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")

@user_router.message(SetDisplayName.entering_display_name)
async def process_display_name_for_existing_user(message: Message, state: FSMContext):
    """Обработка ввода имени для уже зарегистрированного пользователя"""
    display_name = message.text.strip()
    if not display_name:
        await message.answer(f"{E_CROSS} Имя не может быть пустым. Пожалуйста, введите ваше имя и фамилию:", parse_mode="HTML")
        return
    
    if len(display_name) > 50:
        await message.answer(f"{E_CROSS} Слишком длинное имя. Максимум 50 символов.", parse_mode="HTML")
        return
    
    success = await db.update_display_name(message.from_user.id, display_name)
    if success:
        await state.clear()
        await message.answer(
            f"{E_CHECK} Спасибо, {display_name}! Теперь вы можете пользоваться ботом.",
            reply_markup=get_start_keyboard(message.from_user.id),
            parse_mode="HTML"
        )
    else:
        await message.answer(f"{E_CROSS} Произошла ошибка. Пожалуйста, попробуйте еще раз.", parse_mode="HTML")

@user_router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    """Показать справку по команде /help"""
    await state.clear()
    is_open, time_left_msg = is_registration_open()
    total_participants = await db.get_total_participants()
    
    help_text = (
        f"{E_GIFT} <b>Помощь по игре «Тайный Санта»</b>\n\n"
        f"{time_left_msg}\n\n"
        f"{E_FILE} <b>Доступные команды:</b>\n"
        f"• /start - Главное меню\n"
        f"• /help - Справка и правила\n\n"
        f"{E_SPARKLES} <b>Как это работает:</b>\n"
        f"1. Нажмите «Принять участие» {E_GIFT}\n"
        f"2. Получите секретный ключ {E_TAG}\n"
        f"3. Укажите свой пол {E_USER}\n"
        f"4. Введите ваше имя и фамилию\n"
        f"5. Укажите желаемый подарок (до {GIFT_BUDGET} ₽) {E_MONEY}\n"
        f"6. Пришлите ссылку(и) на подарок {E_LINK}\n"
        f"7. Ждите, когда все зарегистрируются {E_HOURGLASS}\n"
        f"8. Узнайте, кому дарить подарок! {E_PARTY}\n\n"
        f"• Бюджет: до <b>{GIFT_BUDGET} ₽</b> {E_MONEY}\n"
        f"• Участников: <b>{total_participants}</b> человек {E_USERS}\n"
        f"• Полная анонимность: всё в секрете! {E_LOCK}"
    )
    await message.answer(help_text, reply_markup=get_help_keyboard(), parse_mode="HTML")

@user_router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery, state: FSMContext):
    """Показать справку"""
    await state.clear()
    is_open, time_left_msg = is_registration_open()
    total_participants = await db.get_total_participants()
    
    help_text = (
        f"{E_GIFT} <b>Помощь по игре «Тайный Санта»</b>\n\n"
        f"{time_left_msg}\n\n"
        f"{E_FILE} <b>Доступные команды:</b>\n"
        f"• /start - Главное меню\n"
        f"• Нажмите кнопки ниже для навигации\n\n"
        f"{E_SPARKLES} <b>Как это работает:</b>\n"
        f"1. Нажмите «Принять участие» {E_GIFT}\n"
        f"2. Получите секретный ключ {E_TAG}\n"
        f"3. Укажите свой пол {E_USER}\n"
        f"4. Введите ваше имя и фамилию\n"
        f"5. Укажите желаемый подарок (до {GIFT_BUDGET} ₽) {E_MONEY}\n"
        f"6. Пришлите ссылку(и) на подарок {E_LINK}\n"
        f"7. Ждите, когда все зарегистрируются {E_HOURGLASS}\n"
        f"8. Узнайте, кому дарить подарок! {E_PARTY}\n\n"
        f"• Бюджет: до <b>{GIFT_BUDGET} ₽</b> {E_MONEY}\n"
        f"• Участников: <b>{total_participants}</b> человек {E_USERS}\n"
        f"• Полная анонимность: всё в секрете! {E_LOCK}"
    )
    
    await callback.message.edit_text(help_text, reply_markup=get_help_keyboard(), parse_mode="HTML")
    await callback.answer()

@user_router.callback_query(F.data == "myinfo")
async def show_myinfo(callback: CallbackQuery, state: FSMContext):
    """Показать информацию о пользователе"""
    await state.clear()
    
    user_data = await db.get_user(callback.from_user.id)
    if not user_data:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Зарегистрироваться", callback_data="participate", icon_custom_emoji_id=emoji_id("gift_give"))
        keyboard.button(text="Назад", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
        keyboard.adjust(1)
        
        await callback.message.edit_text(
            f"{E_CROSS} Вы еще не зарегистрированы.\n\n"
            "Нажмите кнопку ниже, чтобы начать регистрацию:",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    total_participants = await db.get_total_participants()
    
    gender_str = f"Мужской {E_USER}" if user_data.get('gender') == 'male' else f"Женский {E_USER}"
    gender_status = f"Использована {E_CHECK}" if user_data.get('gender_changed') else "Доступна (1 раз)"
    
    display_name_safe = html.escape(user_data.get('display_name', 'Не указано'), quote=False)
    wish_safe = html.escape(user_data.get('wish', 'Не указано'), quote=False)
    
    text = (
        f"{E_GIFT} <b>Ваша анкета Тайного Санты:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{E_USER} <b>Имя:</b> {display_name_safe}\n"
        f"{E_TAG} <b>Секретный ключ:</b> <code>#{user_data['key']}</code>\n"
        f"• <b>Пол:</b> {gender_str}\n\n"
        f"{E_GIFT} <b>Ваше желание:</b>\n"
        f"«{wish_safe}»\n\n"
    )
    wish_link = user_data.get('wish_link', '')
    if wish_link:
        links = format_wish_links(wish_link)
        if "\n" in links:
            text += f"{E_LINK} <b>Ссылки на подарки:</b>\n{links}\n\n"
        else:
            text += f"{E_LINK} <b>Ссылка:</b> {links}\n\n"
    else:
        text += f"{E_LINK} <b>Ссылка:</b> Без ссылки\n\n"
    
    text += (
        f"{E_SETTINGS} <b>Лимиты правок:</b>\n"
        f"• Смена желания: {3 - user_data.get('wish_changes', 0)} из 3 осталось\n"
        f"• Смена пола: {gender_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    if user_data.get('gift_to_gender'):
        gender = user_data['gift_to_gender']
        gender_text = f"парню {E_USER}" if gender == "male" else f"девушке {E_USER}"
        receiver_id = user_data.get('gift_to_user_id')
        receiver_data = await db.get_user(receiver_id) if receiver_id else None
        
        text += (
            f"{E_GIFT_STAR} <b>ВАШ ПОДОПЕЧНЫЙ:</b>\n"
            f"• Вы дарите подарок: <b>{gender_text}</b>\n"
        )
        if receiver_data:
            text += f"• Желание: «{receiver_data.get('wish', 'не указано')}»\n"
            receiver_links = receiver_data.get('wish_link', '')
            if receiver_links:
                formatted_rec = format_wish_links(receiver_links)
                if "\n" in formatted_rec:
                    text += f"• Ссылки на подарок:\n{formatted_rec}\n"
                else:
                    text += f"• Ссылка на подарок: {formatted_rec}\n"
        text += (
            f"\n{E_MONEY} Бюджет: до <b>{GIFT_BUDGET} ₽</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"С наступающим Новым Годом! {E_PARTY}{E_SPARKLES}"
        )
    else:
        count = await db.get_participants_count()
        progress = generate_progress_bar(count, total_participants)
        text += f"{E_HOURGLASS} <b>Статус:</b> ждём регистрации всех участников ({count}/{total_participants})\n   {progress}"
    
    keyboard = InlineKeyboardBuilder()
    if not user_data.get('gift_to_gender'):
        keyboard.button(text="Изменить желание", callback_data="change_wish_menu", icon_custom_emoji_id=emoji_id("edit"))
        keyboard.button(text="Изменить пол", callback_data="change_gender_menu", icon_custom_emoji_id=emoji_id("repeat"))
    keyboard.button(text="Назад в меню", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

@user_router.callback_query(F.data == "participate")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    """Начало процесса регистрации"""
    is_open, status_msg = is_registration_open()
    if not is_open:
        await callback.message.edit_text(
            f"{status_msg}\n\nРегистрация закрыта, вы не можете зарегистрироваться.",
            reply_markup=get_back_keyboard("back_to_main"),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    if await db.is_user_registered(callback.from_user.id):
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Моя анкета", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
        keyboard.button(text="Назад", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
        keyboard.adjust(1)
        
        await callback.message.edit_text(
            f"{E_CHECK} Вы уже зарегистрированы!\n\nНажмите кнопку ниже, чтобы посмотреть вашу анкету:",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    key = await db.generate_unique_key()
    await state.update_data(key=key)
    
    await callback.message.edit_text(
        f"{E_PARTY} <b>Отлично! Вы участвуете в игре «Тайный Санта»!</b>\n"
        f"{E_TAG} Ваш секретный ключ: <code>#{key}</code>\n\n"
        f"{E_FILE} Теперь нужно заполнить анкету о себе.\n"
        f"Пожалуйста, выберите ваш пол:",
        reply_markup=get_gender_keyboard("back_to_main"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.choosing_gender)
    await callback.answer()

@user_router.callback_query(Registration.choosing_gender, F.data.in_(["gender_male", "gender_female"]))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    gender = "male" if callback.data == "gender_male" else "female"
    await state.update_data(gender=gender)
    
    await callback.message.edit_text(
        f"{E_USER} Теперь введите ваше имя и фамилию (как вас называть в классе):\n\n"
        "Например: Иванов Иван",
        reply_markup=get_back_keyboard("back_to_gender_choice"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.entering_display_name)
    await callback.answer()

@user_router.message(Registration.entering_display_name)
async def process_display_name(message: Message, state: FSMContext):
    """Обработка ввода имени и фамилии"""
    display_name = message.text.strip()
    if not display_name:
        await message.answer(f"{E_CROSS} Имя не может быть пустым. Пожалуйста, введите ваше имя и фамилию:", parse_mode="HTML")
        return
    
    if len(display_name) > 50:
        await message.answer(f"{E_CROSS} Слишком длинное имя. Максимум 50 символов.", parse_mode="HTML")
        return
    
    await state.update_data(display_name=display_name)
    
    await message.answer(
        f"{E_EDIT} Отлично, {display_name}! Теперь напишите, что бы вы хотели получить в подарок (до {GIFT_BUDGET} рублей):\n\n"
        "Пример: 'Мягкая игрушка - панда' или 'Книга \"Мастер и Маргарита\"'\n"
        f"Вы можете указать несколько подарков, но общая сумма не должна превышать {GIFT_BUDGET} рублей.\n\n"
        "Просто отправьте сообщение с вашим желанием:",
        reply_markup=get_back_keyboard("back_to_display_name_input"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.entering_wish)

@user_router.callback_query(F.data == "back_to_display_name_input")
async def back_to_display_name_input(callback: CallbackQuery, state: FSMContext):
    """Вернуться к вводу имени из ввода желания"""
    if await state.get_state() != Registration.entering_wish:
        await callback.answer()
        return
    
    data = await state.get_data()
    key = data.get("key", "неизвестно")
    
    await callback.message.edit_text(
        f"{E_TAG} Ваш секретный ключ: <code>#{key}</code>\n\n"
        f"{E_USER} Пожалуйста, введите ваше имя и фамилию:",
        reply_markup=get_back_keyboard("back_to_gender_choice"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.entering_display_name)
    await callback.answer()

@user_router.callback_query(Registration.choosing_gender, F.data == "back_to_main")
async def back_from_gender(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню из выбора пола"""
    await state.clear()
    total_participants = await db.get_total_participants()
    await callback.message.edit_text(
        get_main_menu_text(callback.from_user.first_name, total_participants),
        reply_markup=get_start_keyboard(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

@user_router.message(Registration.entering_wish)
async def process_wish(message: Message, state: FSMContext):
    """Обработка ввода желания"""
    if len(message.text) > 200:
        await message.answer(f"{E_CROSS} Слишком длинное описание. Максимум 200 символов.", parse_mode="HTML")
        return
    
    await state.update_data(wish=message.text)
    
    await message.answer(
        f"{E_LINK} Теперь пришлите ссылку(и) на ваш подарок (до {GIFT_BUDGET} ₽):\n\n"
        "Вы можете отправить ссылки с сайтов Wildberries, Ozon или любого магазина.\n"
        "Разделяйте несколько ссылок переносом строки или запятыми.\n\n"
        "<i>Если ссылки нет, просто нажмите «Без ссылки» ниже или отправьте «-»</i>",
        reply_markup=get_wish_link_keyboard("back_to_wish_input"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.entering_wish_link)

@user_router.callback_query(F.data == "back_to_gender_choice")
async def back_to_gender_choice(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору пола из ввода имени"""
    if await state.get_state() != Registration.entering_display_name:
        await callback.answer()
        return
    
    data = await state.get_data()
    key = data.get("key", "неизвестно")
    
    await callback.message.edit_text(
        f"{E_TAG} Ваш секретный ключ: <code>#{key}</code>\n\nПожалуйста, выберите ваш пол:",
        reply_markup=get_gender_keyboard("back_to_main"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.choosing_gender)
    await callback.answer()

async def _complete_registration(
    user_id: int,
    user_full_name: str,
    first_name: str,
    links_text: str,
    state: FSMContext,
    bot: Bot,
    message_target: Message
):
    """Единая функция финализации регистрации пользователя"""
    data = await state.get_data()
    display_name = data.get("display_name", first_name)
    
    await db.add_user(
        user_id=user_id,
        username=user_full_name,
        gender=data["gender"],
        wish=data["wish"],
        wish_link=links_text,
        key=data["key"],
        display_name=display_name
    )
    
    count = await db.get_participants_count()
    total_participants = await db.get_total_participants()
    progress = generate_progress_bar(count, total_participants)
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Моя анкета", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
    keyboard.button(text="В главное меню", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    gender_str = f"Мужской {E_USER}" if data['gender'] == 'male' else f"Женский {E_USER}"
    links_formatted = format_wish_links(links_text)
    
    display_name_safe = html.escape(display_name, quote=False)
    wish_safe = html.escape(data['wish'], quote=False)
    
    response_text = (
        f"{E_CHECK} <b>Регистрация завершена, {display_name_safe}!</b> {E_PARTY}\n\n"
        f"{E_FILE} <b>Ваша анкета:</b>\n"
        f"{E_USER} Имя: {display_name_safe}\n"
        f"{E_TAG} Секретный ключ: <code>#{data['key']}</code>\n"
        f"• Пол: {gender_str}\n"
        f"{E_GIFT} Желание: «{wish_safe}»\n"
    )
    if links_text:
        response_text += f"{E_LINK} Ссылки: {links_formatted}\n\n"
    else:
        response_text += f"{E_LINK} Ссылки: Без ссылки\n\n"
        
    response_text += (
        f"{E_STATS} Набор участников: <b>{count}/{total_participants}</b>\n   {progress}\n\n"
        f"Как только все соберутся, администратор проведёт распределение подарков!"
    )
    
    await message_target.answer(response_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()
    
    if count == total_participants:
        await notify_admins_registration_complete(bot, count, total_participants)

@user_router.message(Registration.entering_wish_link)
async def process_wish_link(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода ссылки(ок) на подарок и финализация регистрации"""
    text = message.text.strip()
    
    if text.lower() in ("-", "нет", "пропустить", "skip", "нету", "без ссылки", "0"):
        links_text = ""
    else:
        links = []
        for link in re.split(r'[,\n\s]+', text):
            link = link.strip()
            if link:
                if not validate_wish_link(link):
                    await message.answer(
                        f"{E_CROSS} <b>Некорректная ссылка:</b> <code>{link}</code>\n\n"
                        "Пожалуйста, введите корректные ссылки (начинаются с http:// или https://).\n"
                        "Если ссылки нет, нажмите кнопку «Без ссылки» ниже или отправьте «-»:",
                        reply_markup=get_wish_link_keyboard("back_to_wish_input"),
                        parse_mode="HTML"
                    )
                    return
                links.append(link)
        links_text = '\n'.join(links)
    
    await _complete_registration(
        user_id=message.from_user.id,
        user_full_name=message.from_user.full_name,
        first_name=message.from_user.first_name,
        links_text=links_text,
        state=state,
        bot=bot,
        message_target=message
    )

@user_router.callback_query(Registration.entering_wish_link, F.data == "skip_wish_link")
async def skip_wish_link_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Пропуск ввода ссылки по кнопке"""
    await callback.answer()
    await _complete_registration(
        user_id=callback.from_user.id,
        user_full_name=callback.from_user.full_name,
        first_name=callback.from_user.first_name,
        links_text="",
        state=state,
        bot=bot,
        message_target=callback.message
    )

@user_router.callback_query(F.data == "back_to_wish_input")
async def back_to_wish_input(callback: CallbackQuery, state: FSMContext):
    """Вернуться к вводу желания из ввода ссылки"""
    if await state.get_state() != Registration.entering_wish_link:
        await callback.answer()
        return
    
    data = await state.get_data()
    display_name = data.get("display_name", "пользователь")
    gender = data.get("gender", "неизвестно")
    gender_text = f"Мужской {E_USER}" if gender == "male" else f"Женский {E_USER}"
    
    await callback.message.edit_text(
        f"{E_USER} <b>Ваше имя:</b> {display_name}\n"
        f"• <b>Ваш пол:</b> {gender_text}\n\n"
        f"Теперь напишите, что бы вы хотели получить в подарок (до {GIFT_BUDGET} рублей):\n\n"
        "Пример: 'Мягкая игрушка - панда' или 'Книга \"Мастер и Маргарита\"'\n"
        f"Вы можете указать несколько подарков, но общая сумма не должна превышать {GIFT_BUDGET} рублей.\n\n"
        "Просто отправьте сообщение с вашим желанием:",
        reply_markup=get_back_keyboard("back_to_display_name_input"),
        parse_mode="HTML"
    )
    await state.set_state(Registration.entering_wish)
    await callback.answer()

@user_router.callback_query(F.data == "change_wish_menu")
async def change_wish_menu(callback: CallbackQuery, state: FSMContext):
    """Меню изменения желания"""
    user_data = await db.get_user(callback.from_user.id)
    if not user_data:
        await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
        return
    
    if user_data.get('wish_changes', 0) >= 3:
        await callback.answer("❌ Вы уже использовали все 3 изменения желания", show_alert=True)
        return
    
    if user_data.get('gift_to_gender'):
        await callback.answer("❌ Нельзя менять желание после распределения", show_alert=True)
        return
    
    wish_link = user_data.get('wish_link', '')
    formatted_links = format_wish_links(wish_link)
    
    text = (
        f"{E_EDIT} <b>Изменение желания</b>\n\n"
        f"{E_USER} <b>Ваше имя:</b> {user_data.get('display_name', 'Не указано')}\n"
        f"{E_GIFT} <b>Текущее желание:</b> {user_data['wish']}\n"
    )
    
    if "\n" in formatted_links:
        text += f"{E_LINK} <b>Текущие ссылки:</b>\n" + formatted_links + "\n"
    else:
        text += f"{E_LINK} <b>Текущая ссылка:</b> {formatted_links}\n"
    
    text += f"\nОсталось изменений: {3 - user_data.get('wish_changes', 0)}/3\n\n"
    text += f"Напишите новое желание (до {GIFT_BUDGET} рублей):"
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard("myinfo"), parse_mode="HTML")
    await state.set_state(ChangeWish.entering_new_wish)
    await callback.answer()

@user_router.message(ChangeWish.entering_new_wish)
async def process_new_wish(message: Message, state: FSMContext):
    """Обработка нового желания"""
    if len(message.text) > 200:
        await message.answer(f"{E_CROSS} Слишком длинное описание. Максимум 200 символов.", parse_mode="HTML")
        return
    
    await state.update_data(new_wish=message.text)
    await message.answer(
        f"{E_LINK} Теперь пришлите новую ссылку(и) на подарок (до {GIFT_BUDGET} ₽):\n\n"
        "Вы можете отправить несколько ссылок, разделяя их переносом строки или запятыми.\n"
        "<i>Если ссылки нет, нажмите «Без ссылки» ниже или отправьте «-»</i>",
        reply_markup=get_wish_link_keyboard("change_wish_menu"),
        parse_mode="HTML"
    )
    await state.set_state(ChangeWish.entering_new_link)

@user_router.message(ChangeWish.entering_new_link)
async def process_new_wish_link(message: Message, state: FSMContext):
    """Обработка новой ссылки(ок) на подарок"""
    text = message.text.strip()
    
    if text.lower() in ("-", "нет", "пропустить", "skip", "нету", "без ссылки", "0"):
        links_text = ""
    else:
        links = []
        for link in re.split(r'[,\n\s]+', text):
            link = link.strip()
            if link:
                if not validate_wish_link(link):
                    await message.answer(
                        f"{E_CROSS} <b>Некорректная ссылка:</b> <code>{link}</code>\n\n"
                        "Пожалуйста, введите корректные ссылки (начинаются с http:// или https://).\n"
                        "Если ссылки нет, нажмите кнопку «Без ссылки» ниже или отправьте «-»:",
                        reply_markup=get_wish_link_keyboard("change_wish_menu"),
                        parse_mode="HTML"
                    )
                    return
                links.append(link)
        links_text = '\n'.join(links)
    
    data = await state.get_data()
    success = await db.update_wish(
        user_id=message.from_user.id,
        new_wish=data["new_wish"],
        new_link=links_text
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Моя анкета", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
    keyboard.button(text="В главное меню", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    if success:
        user_data = await db.get_user(message.from_user.id)
        links_formatted = format_wish_links(links_text)
        response_text = (
            f"{E_CHECK} <b>Желание успешно обновлено!</b>\n\n"
            f"{E_GIFT} <b>Новое желание:</b> «{data['new_wish']}»\n"
        )
        if links_text:
            response_text += f"{E_LINK} <b>Ссылки:</b> {links_formatted}\n\n"
        else:
            response_text += f"{E_LINK} <b>Ссылки:</b> Без ссылки\n\n"
        response_text += f"{E_EDIT} Использовано изменений: {user_data.get('wish_changes', 0)} из 3"
    else:
        response_text = f"{E_CROSS} Ошибка при изменении желания."
        
    await message.answer(response_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()

@user_router.callback_query(ChangeWish.entering_new_link, F.data == "skip_wish_link")
async def skip_new_wish_link_callback(callback: CallbackQuery, state: FSMContext):
    """Пропуск новой ссылки при изменении желания"""
    await callback.answer()
    data = await state.get_data()
    success = await db.update_wish(
        user_id=callback.from_user.id,
        new_wish=data["new_wish"],
        new_link=""
    )
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Моя анкета", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
    keyboard.button(text="В главное меню", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    if success:
        user_data = await db.get_user(callback.from_user.id)
        response_text = (
            f"{E_CHECK} <b>Желание успешно обновлено!</b>\n\n"
            f"{E_GIFT} <b>Новое желание:</b> «{data['new_wish']}»\n"
            f"{E_LINK} <b>Ссылки:</b> Без ссылки\n\n"
            f"{E_EDIT} Использовано изменений: {user_data.get('wish_changes', 0)} из 3"
        )
    else:
        response_text = f"{E_CROSS} Ошибка при изменении желания."
        
    await callback.message.edit_text(response_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()

@user_router.callback_query(F.data == "change_gender_menu")
async def change_gender_menu(callback: CallbackQuery, state: FSMContext):
    """Меню изменения пола"""
    user_data = await db.get_user(callback.from_user.id)
    if not user_data:
        await callback.answer("❌ Вы не зарегистрированы", show_alert=True)
        return
    
    if user_data.get('gender_changed', False):
        await callback.answer("❌ Вы уже использовали смену пола", show_alert=True)
        return
    
    if user_data.get('gift_to_gender'):
        await callback.answer("❌ Нельзя менять пол после распределения", show_alert=True)
        return
    
    gender_text = f"Мужской {E_USER}" if user_data['gender'] == 'male' else f"Женский {E_USER}"
    text = (
        f"{E_REPEAT} <b>Изменение пола</b>\n\n"
        f"{E_USER} <b>Ваше имя:</b> {user_data.get('display_name', 'Не указано')}\n"
        f"• <b>Текущий пол:</b> {gender_text}\n\n"
        f"Вы можете изменить пол только 1 раз!\n"
        f"Выберите новый пол:"
    )
    await callback.message.edit_text(text, reply_markup=get_gender_keyboard("myinfo"), parse_mode="HTML")
    await state.set_state(ChangeGender.choosing_new_gender)
    await callback.answer()

@user_router.callback_query(ChangeGender.choosing_new_gender, F.data.in_(["gender_male", "gender_female"]))
async def process_new_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора нового пола"""
    new_gender = "male" if callback.data == "gender_male" else "female"
    success = await db.update_gender(user_id=callback.from_user.id, new_gender=new_gender)
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Моя анкета", callback_data="myinfo", icon_custom_emoji_id=emoji_id("gift"))
    keyboard.button(text="В главное меню", callback_data="back_to_main", icon_custom_emoji_id=emoji_id("back"))
    keyboard.adjust(1)
    
    if success:
        gender_text = f"Мужской {E_USER}" if new_gender == "male" else f"Женский {E_USER}"
        await callback.message.edit_text(
            f"{E_CHECK} <b>Пол успешно изменен!</b>\n• Новый пол: {gender_text}",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"{E_CROSS} Ошибка при изменении пола",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
    
    await state.clear()
    await callback.answer()

@user_router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню"""
    await state.clear()
    
    is_registered = await db.is_user_registered(callback.from_user.id)
    user_data = None
    if is_registered:
        user_data = await db.get_user(callback.from_user.id)
        if not user_data.get('display_name'):
            await callback.message.edit_text(
                f"{E_USER} Пожалуйста, введите ваше имя и фамилию (как вас называть в классе):\n\n"
                "Например: Иванов Иван",
                parse_mode="HTML"
            )
            await state.set_state(SetDisplayName.entering_display_name)
            await callback.answer()
            return
    
    total_participants = await db.get_total_participants()
    registered_count = await db.get_participants_count()
    user_key = user_data.get('key') if user_data else None
    display_name = user_data.get('display_name') if user_data and user_data.get('display_name') else callback.from_user.first_name

    await callback.message.edit_text(
        get_main_menu_text(
            first_name=display_name,
            total_participants=total_participants,
            registered_count=registered_count,
            is_registered=is_registered,
            user_key=user_key
        ),
        reply_markup=get_start_keyboard(callback.from_user.id, is_registered=is_registered),
        parse_mode="HTML"
    )
    await callback.answer()
