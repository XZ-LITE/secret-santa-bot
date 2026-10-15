import re
import os
import json
import html
import datetime
import asyncio
import logging
from typing import Tuple, Optional
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from config import DB_PATH, GIFT_BUDGET

from urllib.parse import urlparse
from custom_emojis import (
    E_USER, E_GIFT, E_GIFT_STAR, E_CROSS,
    E_HOURGLASS, E_PARTY, E_TAG,
    E_LINK, E_STATS, E_FILE
)

def check_deanonymization_text(text: str) -> Optional[str]:
    """Проверяет текст анонимного сообщения на попытки деанонимизации или раскрытия контактов/личности.
    Возвращает строку с описанием нарушения или None, если сообщение безопасно.
    """
    if not text:
        return None
    
    lower = text.lower().strip()
    
    # 1. Попытки узнать имя или личность
    name_patterns = [
        r"\bкто ты\b",
        r"\bкак (?:тебя|вас) зовут\b",
        r"\b(?:тво[её]|ваш[ее]) имя\b",
        r"\bскажи (?:сво[её]|тво[её]) имя\b",
        r"\bназови (?:себя|имя)\b",
        r"\bменя зовут\b",
        r"\bмо[её] имя\b",
        r"\bменя\s+[а-яёa-z]+\s+зовут\b",
        r"\bэто я\b",
        r"\bя\s*[-—:]\s*[а-яёa-z]+",
        r"^(?:привет[,! ]+)?я\s+(?!хочу|люблю|буду|думаю|рад|рада|не|уже)[а-яёa-z]+[!?.]*$",
    ]
    for pat in name_patterns:
        if re.search(pat, lower):
            return "сообщение содержит вопрос об имени или попытку назвать себя"

    # 2. Попытки узнать или раскрыть пол
    gender_patterns = [
        r"\bты (?:мальчик|девочка|парень|девушка|мужчина|женщина)\b",
        r"\bвы (?:мальчик|девочка|парень|девушка|мужчина|женщина)\b",
        r"\bкакого ты пола\b",
        r"\bкакой твой пол\b",
        r"\bя (?:мальчик|девочка|парень|девушка)\b",
    ]
    for pat in gender_patterns:
        if re.search(pat, lower):
            return "сообщение содержит вопрос о поле участника"

    # 3. Вопросы о номере/ключе или классе/кабинете
    meta_patterns = [
        r"\bкакой (?:у тебя|твой|ваш) (?:номер|ключ|код)\b",
        r"\bпод каким ты (?:номером|кодом)\b",
        r"\bтвой ключ\b",
        r"\bтвой номер\b",
        r"\bв каком ты классе\b",
        r"\bиз какого ты класса\b",
        r"\bкакой у тебя класс\b",
        r"\bв каком (?:ты )?кабинете\b",
    ]
    for pat in meta_patterns:
        if re.search(pat, lower):
            return "сообщение содержит вопрос о секретном ключе, номере или классе"

    # 4. Ссылки на личные соцсети и мессенджеры
    if re.search(r"@\w{4,}", lower) or re.search(r"t\.me/[\w_]+", lower) or re.search(r"vk\.com/[\w_]+", lower):
        return "сообщение содержит юзернейм или ссылку на социальную сеть"

    # 5. Номера телефонов
    digits_only = re.sub(r"[^\d]", "", text)
    if len(digits_only) >= 10 and not any(mp in lower for mp in ("ozon", "wildberries", "wb.ru", "market.yandex")):
        return "сообщение содержит номер телефона"

    return None

def format_recipient_info_for_santa(receiver_data: dict, anonymity_mode: str) -> str:
    """Форматирует блок информации о подопечном для Санты в зависимости от выбранного режима анонимности:
    - 'code': только персональный код подарка (строгая анонимность)
    - 'name': имя подопечного и код подарка (классический режим)
    - 'gender': пол и код подарка
    """
    receiver_key = receiver_data.get('key', '---')
    if anonymity_mode == "name":
        receiver_name = html.escape(
            receiver_data.get('display_name') or receiver_data.get('username') or f"Участник #{receiver_key}",
            quote=False
        )
        return f"• <b>Вы дарите подарок для:</b> <b>{receiver_name}</b> (Код: <code>#{receiver_key}</code>)\n"
    elif anonymity_mode == "gender":
        gender = receiver_data.get('gender')
        if gender == "male":
            gender_text = f"<b>парню</b> {E_USER}"
        elif gender == "female":
            gender_text = f"<b>девушке</b> {E_USER}"
        else:
            gender_text = f"<b>участнику</b> {E_USER}"
        return f"• <b>Вы дарите подарок:</b> {gender_text} (Код: <code>#{receiver_key}</code>)\n"
    else:  # "code"
        return f"• <b>Код подарка подопечного:</b> <code>#{receiver_key}</code>\n"

def validate_wish_link(link: str) -> bool:
    """Проверяет одну ссылку на корректность"""
    try:
        parsed = urlparse(link.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc) and "." in parsed.netloc
    except Exception:
        return False

def format_wish_links(wish_link: str) -> str:
    """Форматирует несколько ссылок для красивого отображения"""
    if not wish_link:
        return "Нет ссылки"
    
    links = []
    for link in re.split(r'[,\n\s]+', wish_link):
        link = link.strip()
        if link:
            links.append(link)
    
    if len(links) == 1:
        return links[0]
    else:
        formatted = ""
        for i, link in enumerate(links, 1):
            formatted += f"{i}. {link}\n"
        return formatted.strip()

def format_admin_user_info(user_data: dict, user_id: str) -> str:
    """Форматирует информацию о пользователе для админа"""
    display_name = html.escape(user_data.get('display_name') or user_data.get('username', 'Нет имени'), quote=False)
    wish = html.escape(user_data.get('wish', 'Не указано'), quote=False)
    
    info = [
        f"{E_USER} Пользователь: {display_name}",
        f"• ID: <code>{user_id}</code>",
        f"{E_TAG} Ключ: {user_data.get('key', 'Нет ключа')}",
        f"{E_GIFT} Желание: {wish}",
    ]
    
    wish_link = user_data.get('wish_link', '')
    if wish_link:
        links = format_wish_links(wish_link)
        if "\n" in links:
            info.append(f"{E_LINK} Ссылки:")
            info.append(links)
        else:
            info.append(f"{E_LINK} Ссылка: {links}")
    else:
        info.append(f"{E_LINK} Ссылка: Нет ссылки")
    
    gender_val = user_data.get('gender')
    if gender_val == 'male':
        gender_str = "Мужской"
    elif gender_val == 'female':
        gender_str = "Женский"
    else:
        gender_str = "Не указан"

    info.extend([
        f"• Пол: {gender_str}",
        f"• Изменений желания: {user_data.get('wish_changes', 0)}/3",
        "• Смена пола: Использована" if user_data.get('gender_changed', False) else "• Смена пола: Доступна",
    ])
    
    if user_data.get('gift_to_user_id'):
        gift_to = user_data['gift_to_user_id']
        gift_gender = user_data['gift_to_gender']
        gender_text = "мужчине" if gift_gender == "male" else "женщине"
        
        receiver_name = "ID " + str(gift_to)
        if 'gift_to_name' in user_data and user_data['gift_to_name']:
            receiver_name = user_data['gift_to_name']
        
        info.append(f"{E_GIFT} Дарит: {gender_text} ({receiver_name})")
    
    return "\n".join(info)

def format_admin_user_card(
    user_id: int | str,
    user_data: Optional[dict] = None,
    is_registered: bool = True,
    all_users: Optional[dict] = None
) -> str:
    """Форматирует подробную интерактивную карточку участника для админа"""
    if not is_registered or not user_data:
        return (
            f"{E_USER} <b>Карточка участника</b>\n\n"
            f"• <b>Telegram ID:</b> <code>{user_id}</code>\n"
            f"• <b>Статус:</b> {E_HOURGLASS} В списке доступа (анкета ещё не заполнена)\n\n"
            f"<i>Пользователь добавлен в список доступа, но пока не нажал /start для регистрации.</i>"
        )
    
    display_name = html.escape(user_data.get('display_name') or user_data.get('username') or f"ID {user_id}", quote=False)
    username_str = f"@{user_data['username']}" if user_data.get('username') else "не указан"
    key_str = f"#{user_data.get('key')}" if user_data.get('key') else "нет ключа"
    gender_val = user_data.get('gender')
    gender_str = "Мужской" if gender_val == "male" else ("Женский" if gender_val == "female" else "Не указан")
    wish = html.escape(user_data.get('wish', 'Не указано'), quote=False)
    wish_links = format_wish_links(user_data.get('wish_link', ''))
    wish_changes = user_data.get('wish_changes', 0)
    gender_changed = "использована" if user_data.get('gender_changed') else "доступна (1 раз)"
    
    text = (
        f"{E_USER} <b>Карточка участника</b>\n\n"
        f"• <b>Имя:</b> {display_name}\n"
        f"• <b>Telegram:</b> {username_str} (<code>ID: {user_id}</code>)\n"
        f"• <b>Секретный код подарка:</b> <code>{key_str}</code>\n"
        f"• <b>Статус:</b> Зарегистрирован\n"
        f"• <b>Пол:</b> {gender_str}\n"
        f"• <b>Желание:</b> {wish}\n"
    )
    if wish_links and wish_links != "Нет ссылки":
        text += f"• <b>Ссылки:</b>\n{wish_links}\n"
    else:
        text += "• <b>Ссылки:</b> Нет ссылки\n"
        
    text += (
        f"• <b>Лимиты правок:</b> Желание ({wish_changes}/3), Пол ({gender_changed})\n"
    )
    
    # Информация о распределении (кому дарит и кто дарит ему)
    if user_data.get('gift_to_user_id'):
        gift_to_id = user_data['gift_to_user_id']
        gift_to_gender = "мужчине" if user_data.get('gift_to_gender') == "male" else "женщине"
        gift_to_name = user_data.get('gift_to_name')
        if not gift_to_name and all_users and str(gift_to_id) in all_users:
            gift_to_name = all_users[str(gift_to_id)].get('display_name') or all_users[str(gift_to_id)].get('username')
        gift_to_name_str = f" ({gift_to_name})" if gift_to_name else f" (ID: {gift_to_id})"
        text += f"\n{E_GIFT} <b>Кому дарит:</b> {gift_to_gender}{gift_to_name_str}\n"
        
        # Кто дарит ему:
        if all_users:
            santa_id = None
            for other_id, other_data in all_users.items():
                if isinstance(other_data, dict) and other_data.get('gift_to_user_id') == int(user_id):
                    santa_id = other_id
                    break
            if santa_id and santa_id in all_users:
                santa_data = all_users[santa_id]
                santa_name = santa_data.get('display_name') or santa_data.get('username') or f"ID {santa_id}"
                santa_key = f"#{santa_data.get('key')}" if santa_data.get('key') else ""
                text += f"{E_GIFT_STAR} <b>Кто дарит ему:</b> {santa_name} {santa_key}\n"
                
    return text


def get_default_registration_deadline() -> datetime.datetime:
    """Вычисляет дедлайн регистрации по умолчанию (28 декабря текущего или следующего года)"""
    now = datetime.datetime.now()
    deadline = datetime.datetime(now.year, 12, 28, 23, 59, 59)
    if now >= deadline:
        deadline = datetime.datetime(now.year + 1, 12, 28, 23, 59, 59)
    return deadline

def get_registration_deadline() -> datetime.datetime:
    """Получает дедлайн регистрации из базы данных или использует значение по умолчанию"""
    try:
        if os.path.exists(DB_PATH):
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                deadline_str = data.get("settings", {}).get("registration_deadline")
                if deadline_str:
                    return datetime.datetime.fromisoformat(deadline_str)
    except Exception:
        pass
    
    return get_default_registration_deadline()

def is_registration_open() -> Tuple[bool, str]:
    """Проверяет, открыта ли регистрация"""
    now = datetime.datetime.now()
    registration_deadline = get_registration_deadline()
    
    if now > registration_deadline:
        return False, f"{E_CROSS} Регистрация закрыта! Дедлайн был {registration_deadline.strftime('%d.%m.%Y %H:%M')}"
    
    time_left = registration_deadline - now
    days = time_left.days
    hours = time_left.seconds // 3600
    
    if days > 0:
        time_text = f"{days} дней {hours} часов"
    else:
        minutes = (time_left.seconds % 3600) // 60
        time_text = f"{hours} часов {minutes} минут"
    
    return True, f"{E_HOURGLASS} Регистрация открыта! Осталось: {time_text}"

def generate_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Генерирует аккуратный визуальный прогресс-бар"""
    if total <= 0:
        return "░" * length + " 0%"
    percent = min(1.0, max(0.0, current / total))
    filled = int(round(length * percent))
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {int(percent * 100)}%"

def get_main_menu_text(
    first_name: str,
    total_participants: int,
    registered_count: int = 0,
    is_registered: bool = False,
    user_key: Optional[int] = None
) -> str:
    """Получить красивый текст главного меню с адаптацией под статус участника"""
    first_name = html.escape(first_name, quote=False)
    is_open, status_msg = is_registration_open()
    progress = generate_progress_bar(registered_count, total_participants)
    
    if is_registered:
        key_str = f"#{user_key}" if user_key else "—"
        text = (
            f"{E_PARTY} Привет, <b>{first_name}</b>!\n"
            f"Вы участвуете в игре «Тайный Санта»!\n\n"
            f"{E_TAG} Секретный код подарка: <code>{key_str}</code>\n"
            f"{E_STATS} Набор участников: <b>{registered_count}</b> из <b>{total_participants}</b>\n"
            f"   {progress}\n\n"
            f"{status_msg}\n\n"
            f"{E_GIFT} Когда регистрация завершится, бот пришлёт вам вишлист вашего подопечного!"
        )
    else:
        text = (
            f"{E_PARTY} Привет, <b>{first_name}</b>!\n"
            f"Добро пожаловать в игру «Тайный Санта»!\n\n"
            f"{E_STATS} Набрано участников: <b>{registered_count}</b> из <b>{total_participants}</b>\n"
            f"   {progress}\n\n"
            f"{status_msg}\n\n"
            f"{E_FILE} <b>Правила игры:</b>\n"
            f"<blockquote>• Бюджет подарка: до <b>{GIFT_BUDGET} ₽</b>\n"
            f"• Полная тайна: личность Санты остаётся секретом\n"
            f"• Для участия нажмите кнопку «Принять участие»</blockquote>"
        )
    return text

async def send_message_safe(
    target_bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    parse_mode=None
) -> Tuple[bool, Optional[str]]:
    """Безопасная отправка сообщения с обработкой лимитов и блокировок Telegram"""
    try:
        await target_bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True, None
    except TelegramRetryAfter as e:
        logging.warning("Flood control: ожидание %s сек для %s", e.retry_after, chat_id)
        await asyncio.sleep(e.retry_after)
        try:
            await target_bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True, None
        except Exception as retry_err:
            return False, str(retry_err)
    except TelegramForbiddenError:
        logging.warning("Пользователь %s заблокировал бота или чат недоступен", chat_id)
        return False, "Пользователь заблокировал бота"
    except Exception as e:
        logging.error("Ошибка отправки пользователю %s: %s", chat_id, e)
        return False, str(e)
