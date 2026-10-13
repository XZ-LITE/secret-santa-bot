import datetime
import asyncio
import logging
import html
from aiogram import Bot
from config import ADMIN_IDS, GIFT_BUDGET
from utils import format_wish_links, send_message_safe
from database import Database
from custom_emojis import (
    E_CLOCK, E_BELL, E_GIFT, E_GIFT_STAR, E_PARTY, E_SPARKLES,
    E_MONEY, E_STATS, E_CROWN, E_LINK, E_USER
)

async def send_registration_reminders(bot: Bot, db: Database) -> int:
    """Отправляет напоминания незарегистрированным пользователям, возвращает количество отправленных"""
    now = datetime.datetime.now()
    registration_deadline = await db.get_registration_deadline()
    
    if now > registration_deadline:
        return 0
    
    unregistered = await db.get_unregistered_users()
    reminders_sent = 0
    
    for user_id in unregistered:
        try:
            if not await db.is_user_in_allowed_list(user_id):
                continue
                
            last_reminder = await db.get_last_reminder(user_id)
            if last_reminder is None or (now - last_reminder).total_seconds() > 86400:
                days_left = (registration_deadline - now).days
                
                if days_left == 1:
                    message = (
                        f"{E_CLOCK} <b>СРОЧНОЕ НАПОМИНАНИЕ!</b>\n\n"
                        "До закрытия регистрации в Тайном Санте остался <b>1 ДЕНЬ</b>!\n"
                        "Успейте зарегистрироваться до конца завтрашнего дня!\n\n"
                        "Нажмите /start для регистрации."
                    )
                elif days_left <= 3:
                    message = (
                        f"{E_BELL} <b>Напоминание о Тайном Санте!</b>\n\n"
                        f"До закрытия регистрации осталось <b>{days_left} дня</b>!\n"
                        f"Не забудьте зарегистрироваться до {registration_deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
                        "Нажмите /start для регистрации."
                    )
                else:
                    message = (
                        f"{E_BELL} <b>Напоминание о Тайном Санте!</b>\n\n"
                        f"Не забудьте зарегистрироваться до {registration_deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
                        "Нажмите /start для регистрации."
                    )
                
                success, send_error = await send_message_safe(bot, user_id, message, parse_mode="HTML")
                if success:
                    await db.update_last_reminder(user_id)
                    reminders_sent += 1
                    logging.info("Напоминание отправлено пользователю %s", user_id)
                else:
                    logging.warning("Не удалось отправить напоминание пользователю %s: %s", user_id, send_error)
                    continue
                
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logging.error("Ошибка при обработке пользователя %s: %s", user_id, e)
            continue
    
    logging.info("Итог: отправлено %s напоминаний из %s незарегистрированных", reminders_sent, len(unregistered))
    return reminders_sent

async def start_reminder_scheduler(bot: Bot, db: Database):
    """Запускает фоновый планировщик напоминаний (каждые 6 часов)"""
    while True:
        try:
            logging.info("Планировщик напоминаний запущен в %s", datetime.datetime.now())
            sent_count = await send_registration_reminders(bot, db)
            if sent_count > 0:
                logging.info("Отправлено %s напоминаний", sent_count)
            else:
                logging.info("Напоминания не требовались или не были отправлены")
        except Exception as e:
            logging.error("Ошибка в планировщике напоминаний: %s", e)
        
        await asyncio.sleep(6 * 3600)

async def notify_all_participants(bot: Bot, db: Database):
    """Отправляет уведомления всем участникам о том, кому они дарят"""
    users = await db.get_all_users()
    
    for user_id_str, user_data in users.items():
        user_id = int(user_id_str)
        gift_to_id = user_data.get('gift_to_user_id')
        gift_to_gender = user_data.get('gift_to_gender')
        
        if not gift_to_id or not gift_to_gender:
            continue
        
        receiver_data = await db.get_user(gift_to_id)
        if not receiver_data:
            continue
        
        gender_text = f"<b>мужчине</b> {E_USER}" if gift_to_gender == "male" else f"<b>женщине</b> {E_USER}"
        receiver_wish = html.escape(receiver_data.get('wish', 'не указано'), quote=False)
        receiver_links = format_wish_links(receiver_data.get('wish_link', ''))
        
        message = (
            f"{E_GIFT} <b>Внимание! Все участники зарегистрировались!</b>\n\n"
            f"Распределение Тайного Санты завершено! {E_PARTY}{E_SPARKLES}\n\n"
            f"Вы дарите подарок: {gender_text}\n"
            f"Желание получателя: <i>«{receiver_wish}»</i>\n"
        )
        
        if receiver_links and receiver_links != "Нет ссылки":
            if "\n" in receiver_links:
                message += f"\n{E_LINK} <b>Ссылки на подарки:</b>\n"
                for line in receiver_links.split('\n'):
                    if "http" in line:
                        message += f"{line}\n"
            else:
                message += f"\n{E_LINK} <b>Ссылка на подарок:</b> {receiver_links}\n"
        
        message += f"\n{E_MONEY} <b>Бюджет:</b> до {GIFT_BUDGET} рублей\n"
        message += "Не забудьте про творческий подход и новогоднее настроение!\n"
        message += f"С наступающим Новым Годом! {E_PARTY}{E_SPARKLES}"
        
        success, err = await send_message_safe(bot, user_id, message, parse_mode="HTML")
        if not success:
            logging.warning("Не удалось отправить сообщение пользователю %s: %s", user_id, err)
        await asyncio.sleep(0.05)

async def notify_admins_registration_complete(bot: Bot, count: int, total_participants: int):
    """Уведомляет администраторов о том, что все участники зарегистрировались"""
    message = (
        f"{E_PARTY} <b>ВСЕ УЧАСТНИКИ ЗАРЕГИСТРИРОВАЛИСЬ!</b>\n\n"
        f"{E_STATS} <b>Статистика:</b> {count}/{total_participants}\n\n"
        "Для выполнения распределения:\n"
        f"1. Перейдите в админ-панель {E_CROWN}\n"
        "2. Выберите распределение подарков\n\n"
        "После распределения все участники получат уведомления!"
    )
    for admin_id in ADMIN_IDS:
        success, err = await send_message_safe(bot, admin_id, message, parse_mode="HTML")
        if not success:
            logging.warning("Не удалось отправить уведомление админу %s: %s", admin_id, err)
        await asyncio.sleep(0.05)
