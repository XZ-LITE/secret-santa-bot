from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Update
from config import ADMIN_IDS
from database import Database

class AccessMiddleware(BaseMiddleware):
    def __init__(self, database: Database):
        super().__init__()
        self.db = database

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        
        if event.message:
            if event.message.from_user:
                user_id = event.message.from_user.id
            if event.message.text and event.message.text.startswith('/start'):
                return await handler(event, data)
        elif event.callback_query:
            if event.callback_query.from_user:
                user_id = event.callback_query.from_user.id
            callback_data = event.callback_query.data

            if callback_data == "request_access":
                return await handler(event, data)

            is_admin_callback = bool(callback_data) and (
                callback_data.startswith(("admin_", "giver_", "receiver_", "select_", "reset_", "approve_user_", "reject_user_"))
                or callback_data in {"continue_with_selected", "confirm_mixed_distribution"}
            )
            if is_admin_callback:
                if user_id not in ADMIN_IDS:
                    await event.callback_query.answer("Доступ запрещен", show_alert=True)
                    return
                return await handler(event, data)
        
        if user_id:
            has_access = (user_id in ADMIN_IDS) or await self.db.check_access(user_id)
            
            if not has_access:
                try:
                    if event.message:
                        from aiogram.utils.keyboard import InlineKeyboardBuilder
                        from custom_emojis import E_LOCK, emoji_id
                        kb = InlineKeyboardBuilder()
                        kb.button(
                            text="Подать заявку на участие",
                            icon_custom_emoji_id=emoji_id("new_message"),
                            callback_data="request_access"
                        )
                        await event.message.answer(
                            f"{E_LOCK} <b>Доступ ограничен.</b> Этот бот только для участников класса.\n\n"
                            "Вы можете отправить заявку администраторам на доступ к игре:",
                            reply_markup=kb.as_markup(),
                            parse_mode="HTML"
                        )
                    elif event.callback_query:
                        await event.callback_query.answer("Доступ ограничен", show_alert=True)
                except Exception:
                    pass
                return
        
        return await handler(event, data)
