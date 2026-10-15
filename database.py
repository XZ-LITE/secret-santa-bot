import asyncio
import json
import os
import datetime
import hashlib
import random
import logging
from functools import wraps
from typing import Dict, Optional, Tuple, List
import aiofiles
import pandas as pd

from config import BACKUP_DIR, INITIAL_ALLOWED_USERS, DB_PATH, ADMIN_IDS
from utils import format_wish_links, get_default_registration_deadline
from custom_emojis import E_CHECK, E_CROSS, E_HOURGLASS, E_PUZZLE, E_GIFT

def serialize_mutations(method):
    """Декоратор для сериализации параллельных операций записи в БД через asyncio.Lock"""
    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        async with self._mutation_lock:
            return await method(self, *args, **kwargs)
    return wrapper

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._mutation_lock = asyncio.Lock()
        self._ensure_db_dir()
        self._ensure_backup_dir()
    
    def _ensure_db_dir(self):
        """Создает директорию для БД если её нет"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    
    def _ensure_backup_dir(self):
        """Создает директорию для бэкапов если её нет"""
        os.makedirs(BACKUP_DIR, exist_ok=True)
    
    async def _read_db(self) -> Dict:
        """Читает базу данных из JSON файла"""
        try:
            async with aiofiles.open(self.db_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                try:
                    data = json.loads(content) if content else {}
                except json.JSONDecodeError:
                    data = {}
                    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
                    backup_path = f"{self.db_path}.corrupt_{digest}"
                    if not os.path.exists(backup_path):
                        async with aiofiles.open(backup_path, 'w', encoding='utf-8') as backup:
                            await backup.write(content)
                        logging.error("Поврежденная БД сохранена в %s", backup_path)

                if not isinstance(data, dict):
                    data = {}
                if not isinstance(data.get("settings"), dict):
                    data["settings"] = {}
                data["settings"].setdefault("total_participants", 20)
                data["settings"].setdefault("registration_open", True)
                data["settings"].setdefault("moderation_enabled", True)
                data["settings"].setdefault("reveal_done", False)
                if not isinstance(data.get("allowed_users"), list):
                    data["allowed_users"] = INITIAL_ALLOWED_USERS.copy()
                if not isinstance(data.get("users"), dict):
                    data["users"] = {}

                # Добавляем display_name для существующих пользователей
                for user_data in data["users"].values():
                    if isinstance(user_data, dict):
                        user_data.setdefault("display_name", "")
                        user_data.setdefault("gift_to_name", "")

                data.setdefault("auto_distribution_done", False)
                data.setdefault("manual_distributions", [])
                data.setdefault("participants", [])
                data.setdefault("next_key", 10000)
                data.setdefault("reminders_sent", {})
                data.setdefault("access_requests", {})
                data.setdefault("anonymous_notes", [])
                data.setdefault("pending_notes", {})

                if not isinstance(data["participants"], list):
                    data["participants"] = []
                if not isinstance(data["allowed_users"], list):
                    data["allowed_users"] = INITIAL_ALLOWED_USERS.copy()
                if not isinstance(data["manual_distributions"], list):
                    data["manual_distributions"] = []
                if not isinstance(data["reminders_sent"], dict):
                    data["reminders_sent"] = {}
                if not isinstance(data["access_requests"], dict):
                    data["access_requests"] = {}
                if not isinstance(data["anonymous_notes"], list):
                    data["anonymous_notes"] = []
                if not isinstance(data["pending_notes"], dict):
                    data["pending_notes"] = {}
                
                return data
        except FileNotFoundError:
            return {
                "users": {},
                "participants": [],
                "auto_distribution_done": False,
                "manual_distributions": [],
                "next_key": 10000,
                "reminders_sent": {},
                "access_requests": {},
                "anonymous_notes": [],
                "pending_notes": {},
                "settings": {
                    "total_participants": 20,
                    "registration_open": True,
                    "moderation_enabled": True,
                    "reveal_done": False
                },
                "allowed_users": INITIAL_ALLOWED_USERS.copy()
            }
    
    async def _write_db(self, data: Dict):
        """Атомарно записывает данные в JSON файл через временный файл"""
        temp_path = f"{self.db_path}.tmp"
        try:
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(temp_path, self.db_path)
        except Exception as e:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            logging.error("Ошибка записи БД: %s", e)
            raise
    
    async def check_access(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя доступ к боту"""
        if user_id in ADMIN_IDS:
            return True
        data = await self._read_db()
        return user_id in data.get("allowed_users", [])
    
    async def get_allowed_users(self) -> List[int]:
        """Получает список разрешенных пользователей"""
        data = await self._read_db()
        return data.get("allowed_users", [])
    
    @serialize_mutations
    async def add_allowed_user(self, user_id: int) -> bool:
        """Добавляет пользователя в список разрешенных"""
        data = await self._read_db()
        if user_id not in data["allowed_users"]:
            data["allowed_users"].append(user_id)
            await self._write_db(data)
            return True
        return False
    
    @serialize_mutations
    async def remove_allowed_user(self, user_id: int) -> bool:
        """Удаляет пользователя из списка разрешенных"""
        data = await self._read_db()
        if user_id in data["allowed_users"]:
            user_key = str(user_id)
            if user_key in data["users"] and any(
                isinstance(u_data, dict) and u_data.get("gift_to_user_id")
                for u_data in data["users"].values()
            ):
                return False
            data["allowed_users"].remove(user_id)
            if user_key in data["users"]:
                del data["users"][user_key]
            if user_id in data["participants"]:
                data["participants"].remove(user_id)
            await self._write_db(data)
            return True
        return False
    
    async def is_user_in_allowed_list(self, user_id: int) -> bool:
        """Проверяет, есть ли пользователь в списке доступа"""
        data = await self._read_db()
        return user_id in data.get("allowed_users", [])
    
    async def has_pending_access_request(self, user_id: int) -> bool:
        """Проверяет, есть ли ожидающая заявка на доступ"""
        data = await self._read_db()
        return str(user_id) in data.get("access_requests", {})

    @serialize_mutations
    async def add_access_request(self, user_id: int, user_info: dict) -> bool:
        """Добавляет заявку на доступ"""
        data = await self._read_db()
        data.setdefault("access_requests", {})
        data["access_requests"][str(user_id)] = user_info
        await self._write_db(data)
        return True

    @serialize_mutations
    async def remove_access_request(self, user_id: int) -> bool:
        """Удаляет заявку на доступ"""
        data = await self._read_db()
        user_key = str(user_id)
        if user_key in data.get("access_requests", {}):
            del data["access_requests"][user_key]
            await self._write_db(data)
            return True
        return False

    async def get_access_request(self, user_id: int) -> Optional[dict]:
        """Получает данные заявки на доступ"""
        data = await self._read_db()
        return data.get("access_requests", {}).get(str(user_id))

    async def get_all_access_requests(self) -> Dict[str, dict]:
        """Получает все ожидающие заявки на доступ"""
        data = await self._read_db()
        return data.get("access_requests", {})
    
    async def get_total_participants(self) -> int:
        """Получает общее количество участников"""
        data = await self._read_db()
        return data["settings"].get("total_participants", 20)
    
    @serialize_mutations
    async def set_total_participants(self, count: int):
        """Устанавливает общее количество участников"""
        data = await self._read_db()
        data["settings"]["total_participants"] = count
        await self._write_db(data)
    
    async def get_registration_deadline(self) -> datetime.datetime:
        """Получает дедлайн регистрации"""
        data = await self._read_db()
        deadline_str = data["settings"].get("registration_deadline")
        if deadline_str:
            return datetime.datetime.fromisoformat(deadline_str)
        return get_default_registration_deadline()
    
    @serialize_mutations
    async def set_registration_deadline(self, deadline: datetime.datetime):
        """Устанавливает дедлайн регистрации"""
        data = await self._read_db()
        data["settings"]["registration_deadline"] = deadline.isoformat()
        await self._write_db(data)
    
    @serialize_mutations
    async def add_user(self, user_id: int, username: str, gender: str, wish: str, wish_link: str, key: int, display_name: str = ""):
        """Добавляет нового участника"""
        data = await self._read_db()
        
        data["users"][str(user_id)] = {
            "username": username,
            "display_name": display_name,
            "gender": gender,
            "wish": wish,
            "wish_link": wish_link,
            "key": key,
            "gift_to_user_id": None,
            "gift_to_gender": None,
            "gift_to_name": "",
            "registered": True,
            "wish_changes": 0,
            "gender_changed": False,
            "registration_date": datetime.datetime.now().isoformat(),
            "last_reminder": None
        }
        
        if user_id not in data["participants"]:
            data["participants"].append(user_id)
        
        await self._write_db(data)
    
    @serialize_mutations
    async def update_wish(self, user_id: int, new_wish: str, new_link: str) -> bool:
        """Обновляет желание пользователя"""
        data = await self._read_db()
        user_key = str(user_id)
        
        if user_key in data["users"]:
            data["users"][user_key]["wish"] = new_wish
            data["users"][user_key]["wish_link"] = new_link
            data["users"][user_key]["wish_changes"] = data["users"][user_key].get("wish_changes", 0) + 1
            
            await self._write_db(data)
            return True
        return False
    
    @serialize_mutations
    async def update_gender(self, user_id: int, new_gender: str) -> bool:
        """Обновляет пол пользователя"""
        data = await self._read_db()
        user_key = str(user_id)
        
        if user_key in data["users"]:
            data["users"][user_key]["gender"] = new_gender
            data["users"][user_key]["gender_changed"] = True
            
            await self._write_db(data)
            return True
        return False
    
    @serialize_mutations
    async def update_display_name(self, user_id: int, display_name: str) -> bool:
        """Обновляет отображаемое имя пользователя"""
        data = await self._read_db()
        user_key = str(user_id)
        
        if user_key in data["users"]:
            data["users"][user_key]["display_name"] = display_name
            await self._write_db(data)
            return True
        return False
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получает данные пользователя"""
        data = await self._read_db()
        user_data = data["users"].get(str(user_id))
        if user_data and "display_name" not in user_data:
            user_data["display_name"] = ""
        return user_data
    
    async def get_user_by_key(self, key: int) -> Optional[Tuple[int, Dict]]:
        """Находит пользователя по ключу"""
        data = await self._read_db()
        for user_id, user_data in data["users"].items():
            if user_data.get("key") == key:
                if "display_name" not in user_data:
                    user_data["display_name"] = ""
                return int(user_id), user_data
        return None
    
    async def search_users(self, query: str) -> List[Tuple[str, Dict]]:
        """Ищет пользователей по запросу (ID, username, имя, ключ, желание)"""
        data = await self._read_db()
        results = []
        cleaned_query = query.strip().lstrip('#').lstrip('@')
        query_lower = cleaned_query.lower()
        
        seen_ids = set()
        for user_id, user_data in data.get("users", {}).items():
            if not isinstance(user_data, dict):
                continue
            if "display_name" not in user_data:
                user_data["display_name"] = ""
            
            if cleaned_query.isdigit() and user_data.get("key") == int(cleaned_query):
                results.append((user_id, user_data))
                seen_ids.add(str(user_id))
                continue
            
            if cleaned_query == user_id or cleaned_query in user_id:
                results.append((user_id, user_data))
                seen_ids.add(str(user_id))
                continue
            
            username = user_data.get("username", "").lower()
            if query_lower in username:
                results.append((user_id, user_data))
                seen_ids.add(str(user_id))
                continue
            
            display_name = user_data.get("display_name", "").lower()
            if query_lower in display_name:
                results.append((user_id, user_data))
                seen_ids.add(str(user_id))
                continue
            
            wish = user_data.get("wish", "").lower()
            if query_lower in wish:
                results.append((user_id, user_data))
                seen_ids.add(str(user_id))
                continue
        
        for allowed_uid in data.get("allowed_users", []):
            allowed_str = str(allowed_uid)
            if allowed_str not in seen_ids and (cleaned_query == allowed_str or cleaned_query in allowed_str):
                results.append((allowed_str, {"registered": False, "username": "", "display_name": ""}))
                seen_ids.add(allowed_str)
        
        return results
    
    async def is_user_registered(self, user_id: int) -> bool:
        """Проверяет, зарегистрирован ли пользователь"""
        user = await self.get_user(user_id)
        return user is not None and user.get("registered", False)
    
    @serialize_mutations
    async def generate_unique_key(self) -> int:
        """Генерирует уникальный 5-значный ключ"""
        data = await self._read_db()
        
        key = data.get("next_key", 10000)
        data["next_key"] = key + 1
        
        await self._write_db(data)
        return key
    
    @staticmethod
    def _has_complete_distribution(data: Dict) -> bool:
        """Синхронно проверяет, завершено ли полное распределение без нарушений"""
        try:
            participants = [int(user_id) for user_id in data.get("participants", [])]
        except (TypeError, ValueError):
            return False
        if not participants or len(set(participants)) != len(participants):
            return False

        users = data.get("users", {})
        receivers = []
        for giver_id in participants:
            user_data = users.get(str(giver_id))
            if not isinstance(user_data, dict):
                return False
            receiver_id = user_data.get("gift_to_user_id")
            if receiver_id is None:
                return False
            try:
                receiver_id = int(receiver_id)
            except (TypeError, ValueError):
                return False
            if receiver_id == giver_id:
                return False
            receivers.append(receiver_id)

        return len(set(receivers)) == len(participants) and set(receivers) == set(participants)
    
    @serialize_mutations
    async def make_distribution(self) -> bool:
        """Создает автоматическое распределение Тайного Санты для оставшихся участников"""
        data = await self._read_db()
        
        participants = [int(u) for u in data.get("participants", [])]
        users = data.get("users", {})
        
        remaining_givers = []
        for user_id in participants:
            user_key = str(user_id)
            if user_key in users and not users[user_key].get("gift_to_user_id"):
                remaining_givers.append(user_id)
        
        if not remaining_givers:
            return False
        
        already_receivers = []
        for user_id in participants:
            user_key = str(user_id)
            if user_key in users and users[user_key].get("gift_to_user_id"):
                already_receivers.append(int(users[user_key]["gift_to_user_id"]))
        
        remaining_receivers = []
        for user_id in participants:
            user_key = str(user_id)
            if user_key in users and user_id not in already_receivers:
                remaining_receivers.append(user_id)
        
        if len(remaining_givers) != len(remaining_receivers):
            return False

        if any(str(user_id) not in users for user_id in participants):
            return False

        random.shuffle(remaining_givers)
        receiver_to_giver = {}

        def assign_receiver(giver_id: int, seen_receivers: set) -> bool:
            candidates = remaining_receivers.copy()
            random.shuffle(candidates)
            for receiver_id in candidates:
                if receiver_id == giver_id or receiver_id in seen_receivers:
                    continue
                seen_receivers.add(receiver_id)
                previous_giver = receiver_to_giver.get(receiver_id)
                if previous_giver is None or assign_receiver(previous_giver, seen_receivers):
                    receiver_to_giver[receiver_id] = giver_id
                    return True
            return False

        for giver_id in remaining_givers:
            if not assign_receiver(giver_id, set()):
                return False

        giver_to_receiver = {
            giver_id: receiver_id
            for receiver_id, giver_id in receiver_to_giver.items()
        }
        if len(giver_to_receiver) != len(remaining_givers):
            return False

        for giver_id, receiver_id in giver_to_receiver.items():
            receiver_data = data["users"][str(receiver_id)]
            receiver_gender = receiver_data["gender"]
            receiver_name = receiver_data.get("display_name") or receiver_data.get("username", f"ID {receiver_id}")
            
            data["users"][str(giver_id)]["gift_to_user_id"] = receiver_id
            data["users"][str(giver_id)]["gift_to_gender"] = receiver_gender
            data["users"][str(giver_id)]["gift_to_name"] = receiver_name
        
        data["auto_distribution_done"] = self._has_complete_distribution(data)
        
        await self._write_db(data)
        return True
    
    @serialize_mutations
    async def manual_distribution(self, giver_id: int, receiver_id: int) -> bool:
        """Ручное распределение: даритель -> получатель"""
        data = await self._read_db()
        participants = [int(u_id) for u_id in data.get("participants", [])]
        if giver_id not in participants or receiver_id not in participants:
            return False
        
        if str(giver_id) not in data["users"] or str(receiver_id) not in data["users"]:
            return False
        
        if giver_id == receiver_id:
            return False
        
        if data["users"][str(giver_id)].get("gift_to_user_id"):
            return False
        
        for user_id_str, user_data in data["users"].items():
            if user_data.get("gift_to_user_id") == receiver_id:
                return False
        
        receiver_data = data["users"][str(receiver_id)]
        receiver_gender = receiver_data["gender"]
        receiver_name = receiver_data.get("display_name") or receiver_data.get("username", f"ID {receiver_id}")
        
        data["users"][str(giver_id)]["gift_to_user_id"] = receiver_id
        data["users"][str(giver_id)]["gift_to_gender"] = receiver_gender
        data["users"][str(giver_id)]["gift_to_name"] = receiver_name

        already_receivers = {
            user_data.get("gift_to_user_id")
            for user_data in data["users"].values()
            if user_data.get("gift_to_user_id") is not None
        }
        remaining_givers = [
            user_id for user_id in participants
            if not data["users"].get(str(user_id), {}).get("gift_to_user_id")
        ]
        remaining_receivers = [
            user_id for user_id in participants
            if user_id not in already_receivers
        ]
        if len(remaining_givers) != len(remaining_receivers):
            return False
        if len(remaining_givers) == 1 and remaining_givers[0] == remaining_receivers[0]:
            return False
        
        if "manual_distributions" not in data:
            data["manual_distributions"] = []
        
        data["manual_distributions"].append({
            "giver_id": giver_id,
            "receiver_id": receiver_id,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        data["auto_distribution_done"] = self._has_complete_distribution(data)
        
        await self._write_db(data)
        return True
    
    async def get_all_users(self) -> Dict:
        """Получает всех пользователей (для админа)"""
        data = await self._read_db()
        for user_id, user_data in data.get("users", {}).items():
            if "display_name" not in user_data:
                user_data["display_name"] = ""
        return data.get("users", {})
    
    async def get_participants_count(self) -> int:
        """Возвращает количество зарегистрированных участников"""
        data = await self._read_db()
        return len(data.get("participants", []))
    
    async def is_distribution_done(self) -> bool:
        """Проверяет, выполнено ли распределение"""
        data = await self._read_db()
        return self._has_complete_distribution(data)
    
    async def can_perform_auto_distribution(self) -> Tuple[bool, str]:
        """Проверяет, можно ли выполнить автоматическое распределение"""
        count = await self.get_participants_count()
        total_participants = await self.get_total_participants()
        
        if count < total_participants:
            return False, f"{E_CROSS} <b>Недостаточно участников!</b> Зарегистрировано: <b>{count}/{total_participants}</b>"
        
        if await self.is_distribution_done():
            return False, f"{E_CROSS} <b>Все участники уже распределены!</b>"
        
        data = await self._read_db()
        participants = data.get("participants", [])
        users = data.get("users", {})
        
        remaining_givers = []
        for user_id in participants:
            user_key = str(user_id)
            if user_key in users and not users[user_key].get("gift_to_user_id"):
                remaining_givers.append(user_id)
        
        if not remaining_givers:
            return False, f"{E_CROSS} <b>Все участники уже распределены!</b>"
        
        if len(remaining_givers) == 1:
            return False, f"{E_CROSS} Остался только один участник для распределения. Нужно распределить его вручную."
        
        return True, f"{E_CHECK} Можно выполнить автоматическое распределение для оставшихся {len(remaining_givers)} участников"
    
    async def get_distribution_status(self) -> str:
        """Получает статус распределения"""
        data = await self._read_db()
        
        status = []
        if self._has_complete_distribution(data):
            status.append(f"{E_CHECK} Распределение завершено")
        else:
            status.append(f"{E_HOURGLASS} Распределение не завершено")
        
        manual_distributions = data.get("manual_distributions", [])
        status.append(f"{E_PUZZLE} Ручных распределений: <b>{len(manual_distributions)}</b>")
        
        participants = data.get("participants", [])
        users = data.get("users", {})
        distributed = sum(1 for u in users.values() if u.get("gift_to_user_id"))
        
        status.append(f"{E_GIFT} Распределено участников: <b>{distributed}/{len(participants)}</b>")
        
        remaining_givers = []
        for user_id in participants:
            user_key = str(user_id)
            if user_key in users and not users[user_key].get("gift_to_user_id"):
                remaining_givers.append(user_id)
        
        if remaining_givers:
            status.append(f"{E_HOURGLASS} Осталось распределить: <b>{len(remaining_givers)}</b> участников")
        
        return "\n".join(status)
    
    @serialize_mutations
    async def reset_distribution(self) -> bool:
        """Сбрасывает распределение (для админа)"""
        data = await self._read_db()
        
        has_distribution = (
            data.get("auto_distribution_done")
            or data.get("manual_distributions")
            or any(
                user_data.get("gift_to_user_id")
                for user_data in data.get("users", {}).values()
                if isinstance(user_data, dict)
            )
        )
        
        if not has_distribution:
            return False
        
        data["auto_distribution_done"] = False
        data["manual_distributions"] = []
        data.setdefault("settings", {})["reveal_done"] = False
        data["pending_notes"] = {}
        
        for user_id in data["users"]:
            data["users"][user_id]["gift_to_user_id"] = None
            data["users"][user_id]["gift_to_gender"] = None
            data["users"][user_id]["gift_to_name"] = ""
        
        await self._write_db(data)
        return True
    
    async def get_unregistered_users(self) -> list:
        """Получает список незарегистрированных пользователей с доступом к боту"""
        data = await self._read_db()
        allowed_users = data.get("allowed_users", [])
        registered_ids = [int(uid) for uid in data.get("users", {}).keys()]
        
        unregistered = [uid for uid in allowed_users if uid not in registered_ids]
        return unregistered
    
    @serialize_mutations
    async def update_last_reminder(self, user_id: int):
        """Обновляет дату последнего напоминания"""
        data = await self._read_db()
        if "reminders_sent" not in data:
            data["reminders_sent"] = {}
        data["reminders_sent"][str(user_id)] = datetime.datetime.now().isoformat()
        await self._write_db(data)
    
    async def get_last_reminder(self, user_id: int) -> Optional[datetime.datetime]:
        """Получает дату последнего напоминания"""
        data = await self._read_db()
        reminder_str = data.get("reminders_sent", {}).get(str(user_id))
        if reminder_str:
            return datetime.datetime.fromisoformat(reminder_str)
        return None
    
    async def create_backup(self) -> str:
        """Создает резервную копию базы данных"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        
        data = await self._read_db()
        
        async with aiofiles.open(backup_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        
        return backup_path
    
    async def export_to_excel(self) -> str:
        """Экспортирует данные в Excel"""
        data = await self._read_db()
        users = data.get("users", {})
        
        excel_data = []
        for user_id, user_data in users.items():
            row = {
                "ID": user_id,
                "Имя": user_data.get("username", ""),
                "Отображаемое имя": user_data.get("display_name", ""),
                "Ключ": user_data.get("key", ""),
                "Пол": "Мужской" if user_data.get("gender") == "male" else ("Женский" if user_data.get("gender") == "female" else "Не указан"),
                "Желание": user_data.get("wish", ""),
                "Изменений желания": user_data.get("wish_changes", 0),
                "Смена пола": "Да" if user_data.get("gender_changed", False) else "Нет",
                "Дата регистрации": user_data.get("registration_date", ""),
            }
            
            wish_link = user_data.get("wish_link", "")
            row["Ссылки"] = format_wish_links(wish_link) if wish_link else "Нет ссылок"
            
            if user_data.get("gift_to_user_id"):
                row["Дарит ID"] = user_data["gift_to_user_id"]
                row["Дарит имя"] = user_data.get("gift_to_name", "")
                row["Дарит полу"] = "Мужской" if user_data.get("gift_to_gender") == "male" else "Женский"
            
            excel_data.append(row)
        
        df = pd.DataFrame(excel_data)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = os.path.join(BACKUP_DIR, f"export_{timestamp}.xlsx")
        
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Участники', index=False)
            
            worksheet = writer.sheets['Участники']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if cell.value and len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                adjusted_width = min(max(max_length + 2, 10), 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        return excel_path
    
    @serialize_mutations
    async def reset_user_changes(self, user_id: int, reset_type: str = "all") -> bool:
        """Сбрасывает счетчики изменений пользователя"""
        data = await self._read_db()
        user_key = str(user_id)
        
        if user_key not in data["users"]:
            return False
        
        if data["users"][user_key].get("gift_to_user_id"):
            return False
        
        if reset_type in ("wish", "all"):
            data["users"][user_key]["wish_changes"] = 0
        
        if reset_type in ("gender", "all"):
            data["users"][user_key]["gender_changed"] = False
        
        await self._write_db(data)
        return True
    
    async def get_remaining_users_for_distribution(self) -> Tuple[List[int], List[int]]:
        """Получает списки участников, которые еще не распределены как дарители и получатели"""
        data = await self._read_db()
        participants = [int(u) for u in data.get("participants", [])]
        users = data.get("users", {})
        
        remaining_givers = [
            user_id for user_id in participants
            if str(user_id) in users and not users[str(user_id)].get("gift_to_user_id")
        ]
        
        already_receivers = [
            int(users[str(user_id)]["gift_to_user_id"])
            for user_id in participants
            if str(user_id) in users and users[str(user_id)].get("gift_to_user_id")
        ]
        
        remaining_receivers = [
            user_id for user_id in participants
            if str(user_id) in users and user_id not in already_receivers
        ]
        
        return remaining_givers, remaining_receivers

    async def get_santa_for_user(self, receiver_id: int) -> Optional[int]:
        """Возвращает Telegram ID Тайного Санты для указанного получателя"""
        data = await self._read_db()
        users = data.get("users", {})
        receiver_id_int = int(receiver_id)
        for giver_id, user_data in users.items():
            if isinstance(user_data, dict) and user_data.get("gift_to_user_id") == receiver_id_int:
                return int(giver_id)
        return None

    async def get_receiver_for_user(self, giver_id: int) -> Optional[int]:
        """Возвращает Telegram ID получателя для указанного Санты"""
        data = await self._read_db()
        user_data = data.get("users", {}).get(str(giver_id))
        if isinstance(user_data, dict):
            rec = user_data.get("gift_to_user_id")
            return int(rec) if rec is not None else None
        return None

    @serialize_mutations
    async def save_anonymous_note(self, from_user_id: int, to_user_id: int, note_type: str, text: str) -> None:
        """Сохраняет анонимную записку (вопрос или ответ) в историю"""
        data = await self._read_db()
        if "anonymous_notes" not in data or not isinstance(data["anonymous_notes"], list):
            data["anonymous_notes"] = []
        data["anonymous_notes"].append({
            "from_user_id": int(from_user_id),
            "to_user_id": int(to_user_id),
            "type": note_type,
            "text": text,
            "timestamp": datetime.datetime.now().isoformat()
        })
        if len(data["anonymous_notes"]) > 500:
            data["anonymous_notes"] = data["anonymous_notes"][-500:]
        await self._write_db(data)

    async def check_anonymous_rate_limit(self, from_user_id: int, limit: int = 5, window_seconds: int = 60) -> bool:
        """Проверяет, не превысил ли пользователь лимит отправки записок (по умолчанию 5 в минуту)"""
        data = await self._read_db()
        notes = data.get("anonymous_notes", [])
        if not isinstance(notes, list):
            return True
        now = datetime.datetime.now()
        count = 0
        from_id = int(from_user_id)
        for note in reversed(notes):
            if note.get("from_user_id") == from_id:
                try:
                    note_time = datetime.datetime.fromisoformat(note.get("timestamp", ""))
                    if (now - note_time).total_seconds() <= window_seconds:
                        count += 1
                        if count >= limit:
                            return False
                    else:
                        break
                except Exception:
                    pass
        return True

    async def get_anonymous_notes(self) -> List[Dict]:
        """Возвращает историю анонимных записок"""
        data = await self._read_db()
        return data.get("anonymous_notes", [])

    async def is_moderation_enabled(self) -> bool:
        """Проверяет, включена ли премодерация записок админом"""
        data = await self._read_db()
        return data.get("settings", {}).get("moderation_enabled", True)

    @serialize_mutations
    async def toggle_moderation(self) -> bool:
        """Переключает статус премодерации записок (ВКЛ / ВЫКЛ)"""
        data = await self._read_db()
        current = data.get("settings", {}).get("moderation_enabled", True)
        data.setdefault("settings", {})["moderation_enabled"] = not current
        await self._write_db(data)
        return not current

    async def is_reveal_done(self) -> bool:
        """Проверяет, было ли выполнено финальное раскрытие Санты"""
        data = await self._read_db()
        return data.get("settings", {}).get("reveal_done", False)

    @serialize_mutations
    async def set_reveal_done(self, done: bool = True) -> None:
        """Устанавливает статус финального раскрытия Санты"""
        data = await self._read_db()
        data.setdefault("settings", {})["reveal_done"] = done
        await self._write_db(data)

    @serialize_mutations
    async def save_pending_note(
        self,
        note_id: str,
        sender_id: int,
        target_id: int,
        note_type: str,
        text: str,
        sender_role: str = "santa"
    ) -> None:
        """Сохраняет записку в очередь премодерации"""
        data = await self._read_db()
        if "pending_notes" not in data or not isinstance(data["pending_notes"], dict):
            data["pending_notes"] = {}
        data["pending_notes"][note_id] = {
            "note_id": note_id,
            "sender_id": int(sender_id),
            "target_id": int(target_id),
            "note_type": note_type,
            "sender_role": sender_role,
            "text": text,
            "created_at": datetime.datetime.now().isoformat()
        }
        await self._write_db(data)

    async def get_pending_note(self, note_id: str) -> Optional[Dict]:
        """Получает записку из очереди модерации без удаления"""
        data = await self._read_db()
        return data.get("pending_notes", {}).get(note_id)

    @serialize_mutations
    async def pop_pending_note(self, note_id: str) -> Optional[Dict]:
        """Извлекает и удаляет записку из очереди модерации"""
        data = await self._read_db()
        pending = data.get("pending_notes", {})
        if note_id in pending:
            note = pending.pop(note_id)
            await self._write_db(data)
            return note
        return None

    async def get_distribution_pairs(self) -> List[Dict]:
        """Возвращает список пар распределения (даритель -> получатель) с полной информацией"""
        data = await self._read_db()
        users = data.get("users", {})
        pairs = []
        for giver_id_str, giver_data in users.items():
            if not isinstance(giver_data, dict):
                continue
            receiver_id = giver_data.get("gift_to_user_id")
            if not receiver_id:
                continue
            receiver_data = users.get(str(receiver_id), {})
            pairs.append({
                "giver_id": int(giver_id_str),
                "giver_name": giver_data.get("display_name") or giver_data.get("username", f"ID {giver_id_str}"),
                "giver_key": giver_data.get("key"),
                "receiver_id": int(receiver_id),
                "receiver_name": receiver_data.get("display_name") or receiver_data.get("username", f"ID {receiver_id}"),
                "receiver_key": receiver_data.get("key"),
                "receiver_wish": receiver_data.get("wish", "Не указано"),
            })
        return pairs

# Глобальный экземпляр базы данных
db = Database(DB_PATH)
