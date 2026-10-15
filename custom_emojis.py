"""
Модуль поддержки премиум эмодзи Telegram (пак tgiosicons / Telegram iOS Icons, 400 иконок)
По гайду: https://emoji.wivvi.net и справочнику id.txt

Правила:
- В боте ВООБЩЕ нет обычных эмодзи.
- В сообщениях: ТОЛЬКО премиум эмодзи <tg-emoji emoji-id="ID">fallback</tg-emoji> (parse_mode="HTML")
- В кнопках (InlineKeyboardButton / KeyboardButton):
  текст строго без эмодзи, иконка передаётся через icon_custom_emoji_id="ID"
- Во всплывающих окнах callback.answer(..., show_alert=True):
  используется чистый текст без обычных эмодзи (Telegram alert не рендерит кастомные эмодзи).
"""

import os
import re
from typing import Dict, Tuple, Optional

# Основные алиасы для удобного использования в коде (все ID строго из id.txt)
EMOJI_DATA: Dict[str, Tuple[str, str]] = {
    "gift": ("🎁", "6032644646587338669"),
    "gift_give": ("🎁", "5805298713211447980"),
    "gift_star": ("🎁", "5773677501825945508"),
    "check": ("✅", "5774022692642492953"),
    "cross": ("❌", "5774077015388852135"),
    "erase": ("❌", "6030757850274336631"),
    "trash": ("🗑", "6039522349517115015"),
    "user": ("👤", "6035084557378654059"),
    "users": ("👥", "6032609071373226027"),
    "add_user": ("➕", "6033108709213736873"),
    "group": ("👥", "6032594876506312598"),
    "settings": ("⚙", "6032742198179532882"),
    "stats": ("📊", "5936143551854285132"),
    "chart": ("📈", "5938539885907415367"),
    "bell": ("🔔", "6039486778597970865"),
    "remind": ("🔔", "6039677157318332604"),
    "megaphone": ("📢", "6021418126061605425"),
    "broadcast": ("📣", "6039450962865688331"),
    "message": ("💬", "6030784887093464891"),
    "new_message": ("💬", "6030622631818956594"),
    "edit": ("✏️", "6039779802741739617"),
    "pencil": ("✏", "6039614175917903752"),
    "search": ("🔎", "6032850693348399258"),
    "calendar": ("📅", "5890937706803894250"),
    "schedule": ("📅", "5891100675042974129"),
    "clock": ("⏰️", "5983150113483134607"),
    "hourglass": ("⌛️", "5891211339170326418"),
    "lock": ("🔒", "6037249452824072506"),
    "unlock": ("🔓", "6037496202990194718"),
    "crown": ("👑", "5805553606635559688"),
    "dice": ("🔣", "5764638872000533034"),
    "puzzle": ("🧩", "5837069325034331827"),
    "party": ("🎉", "6041731551845159060"),
    "link": ("🔗", "6028171274939797252"),
    "back": ("⬅️", "5960671702059848143"),
    "forward": ("➡️", "6037622221625626773"),
    "exit": ("🚪", "6035130900075777681"),
    "repeat": ("🔁", "6030657343744644592"),
    "money": ("💰", "5904359114531675993"),
    "file": ("📁", "6037475557082403885"),
    "archive": ("📥", "6041730074376410123"),
    "copy": ("📄", "6034969813032374911"),
    "sparkles": ("✨", "5890925363067886150"),
    "magic": ("🪄", "6021792097454002931"),
    "info": ("ℹ", "6028435952299413210"),
    "warning": ("❗️", "6030563507299160824"),
    "question": ("❓", "6030848053177486888"),
    "target": ("🎯", "6032949275732742941"),
    "hello": ("👋", "6041921818896372382"),
    "like": ("👍", "6041720006973067267"),
    "star": ("⭐️", "6034923938486684992"),
    "telegram": ("✈️", "6028346797368283073"),
    "tag": ("🏷", "5886285355279193209"),
    "bot": ("🤖", "6030400221232501136"),
}

# Динамический реестр всех 400 иконок из id.txt:
# Поиск возможен по: slug ("gift"), русскому названию ("Подарок"), или напрямую по ID ("6032644646587338669")
ALL_EMOJIS_BY_ID: Dict[str, Tuple[str, str]] = {}
ALL_EMOJIS_BY_NAME: Dict[str, Tuple[str, str]] = {}
ALL_EMOJIS_BY_CHAR: Dict[str, Tuple[str, str]] = {}

def _load_all_emojis():
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "data", "emojis_id.txt"),
        os.path.join(os.path.dirname(__file__), "..", "Desktop", "id.txt"),
        r"e:\XZ_L1TE\Desktop\id.txt"
    ]
    txt_path = None
    for p in possible_paths:
        if os.path.exists(p):
            txt_path = p
            break
            
    if not txt_path:
        return

    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"^(.*?)\s+(\d+)$", line)
                if m:
                    text_part, eid = m.groups()
                    m2 = re.match(r"^(\S+)\s+(.*)$", text_part)
                    if m2:
                        emo, title = m2.groups()
                    else:
                        emo, title = "", text_part
                    ALL_EMOJIS_BY_ID[eid] = (emo, title)
                    ALL_EMOJIS_BY_NAME[title.strip().lower()] = (emo, eid)
                    if emo and emo.strip():
                        ALL_EMOJIS_BY_CHAR[emo.strip()] = (emo.strip(), eid)
    except Exception:
        pass

    # Основные алиасы имеют высший приоритет для замены символов
    for key, (emo, eid) in EMOJI_DATA.items():
        if emo and emo.strip():
            ALL_EMOJIS_BY_CHAR[emo.strip()] = (emo.strip(), eid)

_load_all_emojis()

def emoji_id(name_or_id: str) -> str:
    """Возвращает строковый ID премиум эмодзи для icon_custom_emoji_id.
    Принимает:
    - Ключ алиаса (например, 'gift', 'check', 'cross')
    - Русское название из id.txt (например, 'Подарок', 'Галочка')
    - Прямой строковый ID
    """
    if not name_or_id:
        return ""
    
    val = str(name_or_id).strip()
    if val.isdigit():
        return val
        
    if val in EMOJI_DATA:
        return EMOJI_DATA[val][1]
        
    lower = val.lower()
    if lower in ALL_EMOJIS_BY_NAME:
        return ALL_EMOJIS_BY_NAME[lower][1]
        
    return ""

def emoji_tag(name_or_id: str, fallback: Optional[str] = None) -> str:
    """Возвращает HTML-тег премиум эмодзи для текста сообщения:
    <tg-emoji emoji-id="ID">fallback</tg-emoji>
    """
    if not name_or_id:
        return ""
        
    val = str(name_or_id).strip()
    eid = ""
    fb = fallback
    
    if val.isdigit():
        eid = val
        if eid in ALL_EMOJIS_BY_ID and not fb:
            fb = ALL_EMOJIS_BY_ID[eid][0]
    elif val in EMOJI_DATA:
        fb_default, eid = EMOJI_DATA[val]
        if not fb:
            fb = fb_default
    else:
        lower = val.lower()
        if lower in ALL_EMOJIS_BY_NAME:
            fb_default, eid = ALL_EMOJIS_BY_NAME[lower]
            if not fb:
                fb = fb_default
                
    if not eid:
        return ""
    if not fb:
        fb = "✨"
        
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

def render_text_with_custom_emojis(html_text: str) -> str:
    """Обрабатывает HTML-текст сообщения для рассылок и уведомлений:
    1. Сохраняет существующие теги разметки (<b>, <i>, <code>, <a>, <blockquote>)
    2. Сохраняет нативные кастомные эмодзи Telegram (<tg-emoji emoji-id="...">...</tg-emoji>)
    3. Преобразует шорткоды :код: (например, :gift:, :party:, :подарок:, :6032644646587338669:) в <tg-emoji>
    4. Преобразует стандартные юникод-эмодзи в премиум-эмодзи из пака, если есть соответствие
    """
    if not html_text:
        return ""
        
    tokens = re.split(r'(<tg-emoji[^>]*>.*?</tg-emoji>|<[^>]+>)', html_text, flags=re.DOTALL)
    out = []
    
    for token in tokens:
        if not token:
            continue
        # HTML-тег или готовый блок <tg-emoji> оставляем без изменений
        if token.startswith('<') and token.endswith('>'):
            out.append(token)
            continue
            
        res = token
        
        # 1. Замена шорткодов :код: / :название: / :id:
        def repl_sc(m):
            code = m.group(1).strip()
            tag = emoji_tag(code)
            return tag if tag else m.group(0)
            
        res = re.sub(r':([a-zA-Z0-9_\u0400-\u04FF\s\-]+):', repl_sc, res)
        
        # 2. Преобразование обычных юникод-эмодзи в кастомные премиум-эмодзи
        sub_tokens = re.split(r'(<tg-emoji[^>]*>.*?</tg-emoji>)', res, flags=re.DOTALL)
        rendered_sub = []
        for st in sub_tokens:
            if st.startswith('<tg-emoji') and st.endswith('</tg-emoji>'):
                rendered_sub.append(st)
            else:
                s = st
                for emo_char, (fallback, eid) in sorted(ALL_EMOJIS_BY_CHAR.items(), key=lambda x: len(x[0]), reverse=True):
                    if emo_char in s:
                        s = s.replace(emo_char, f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>')
                rendered_sub.append(s)
                
        out.append("".join(rendered_sub))
        
    return "".join(out)

# Предопределённые премиум константы для текста сообщений (HTML)
E_GIFT = emoji_tag("gift")
E_GIFT_STAR = emoji_tag("gift_star")
E_GIFT_GIVE = emoji_tag("gift_give")
E_CHECK = emoji_tag("check")
E_CROSS = emoji_tag("cross")
E_ERASE = emoji_tag("erase")
E_TRASH = emoji_tag("trash")
E_USER = emoji_tag("user")
E_USERS = emoji_tag("users")
E_ADD_USER = emoji_tag("add_user")
E_SETTINGS = emoji_tag("settings")
E_STATS = emoji_tag("stats")
E_CHART = emoji_tag("chart")
E_BELL = emoji_tag("bell")
E_REMIND = emoji_tag("remind")
E_MEGAPHONE = emoji_tag("megaphone")
E_BROADCAST = emoji_tag("broadcast")
E_MESSAGE = emoji_tag("message")
E_NEW_MESSAGE = emoji_tag("new_message")
E_EDIT = emoji_tag("edit")
E_SEARCH = emoji_tag("search")
E_CALENDAR = emoji_tag("calendar")
E_CLOCK = emoji_tag("clock")
E_HOURGLASS = emoji_tag("hourglass")
E_LOCK = emoji_tag("lock")
E_UNLOCK = emoji_tag("unlock")
E_CROWN = emoji_tag("crown")
E_DICE = emoji_tag("dice")
E_PUZZLE = emoji_tag("puzzle")
E_PARTY = emoji_tag("party")
E_LINK = emoji_tag("link")
E_BACK = emoji_tag("back")
E_FORWARD = emoji_tag("forward")
E_REPEAT = emoji_tag("repeat")
E_MONEY = emoji_tag("money")
E_FILE = emoji_tag("file")
E_ARCHIVE = emoji_tag("archive")
E_COPY = emoji_tag("copy")
E_SPARKLES = emoji_tag("sparkles")
E_MAGIC = emoji_tag("magic")
E_INFO = emoji_tag("info")
E_WARNING = emoji_tag("warning")
E_QUESTION = emoji_tag("question")
E_TARGET = emoji_tag("target")
E_HELLO = emoji_tag("hello")
E_LIKE = emoji_tag("like")
E_STAR = emoji_tag("star")
E_TELEGRAM = emoji_tag("telegram")
E_TAG = emoji_tag("tag")
E_BOT = emoji_tag("bot")
