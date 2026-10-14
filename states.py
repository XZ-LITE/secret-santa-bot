from aiogram.fsm.state import State, StatesGroup

class AnonymousChatSanta(StatesGroup):
    entering_question = State()

class AnonymousChatReceiver(StatesGroup):
    entering_reply = State()

class Registration(StatesGroup):
    choosing_gender = State()
    entering_display_name = State()
    entering_wish = State()
    entering_wish_link = State()

class ChangeWish(StatesGroup):
    entering_new_wish = State()
    entering_new_link = State()

class ChangeGender(StatesGroup):
    choosing_new_gender = State()

class SetDisplayName(StatesGroup):
    entering_display_name = State()

class AdminAddUser(StatesGroup):
    entering_user_id = State()

class AdminRemoveUser(StatesGroup):
    entering_user_id = State()

class AdminSetParticipants(StatesGroup):
    entering_count = State()

class AdminSearchUser(StatesGroup):
    entering_query = State()

class AdminSetDeadline(StatesGroup):
    entering_date = State()
    entering_time = State()

class AdminNotifyAll(StatesGroup):
    entering_message = State()

class AdminNotifyAllUsers(StatesGroup):
    entering_message = State()

class AdminEditDisplayName(StatesGroup):
    entering_user_id = State()
    entering_display_name = State()

class AdminManualDistribution(StatesGroup):
    selecting_giver = State()
    selecting_receiver = State()

class AdminNotifySelected(StatesGroup):
    selecting_users = State()
    entering_message = State()

class AdminResetUserChanges(StatesGroup):
    entering_user_id = State()
    choosing_reset_type = State()

class AdminDirectMessage(StatesGroup):
    entering_message = State()

