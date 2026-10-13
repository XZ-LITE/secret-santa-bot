#!/usr/bin/env bash

# ==============================================================================
# Скрипт автоматической установки бота «Тайный Санта» на VPS (Ubuntu / Debian)
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "=========================================================="
echo "    🎅 УСТАНОВЩИК TELEGRAM-БОТА «ТАЙНЫЙ САНТА» ДЛЯ VPS    "
echo "=========================================================="
echo -e "${NC}"

# Проверка прав суперпользователя (root)
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️ Скрипт запущен не от root. Проверяем наличие sudo...${NC}"
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "${RED}❌ Для установки необходимы права root или утилита sudo.${NC}"
        exit 1
    fi
else
    SUDO=""
fi

# Определение рабочей директории
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo -e "${BLUE}▶ [1/5] Проверка и установка системных зависимостей...${NC}"
if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq >/dev/null 2>&1 || true
    $SUDO apt-get install -y -qq curl git ca-certificates gnupg >/dev/null 2>&1 || true
fi

# Проверка и установка Docker
echo -e "${BLUE}▶ [2/5] Проверка окружения Docker...${NC}"
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${YELLOW}Docker не найден. Устанавливаем официальный Docker...${NC}"
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    $SUDO sh /tmp/get-docker.sh >/dev/null 2>&1
    rm -f /tmp/get-docker.sh
    $SUDO systemctl enable --now docker >/dev/null 2>&1
    echo -e "${GREEN}✓ Docker успешно установлен!${NC}"
else
    echo -e "${GREEN}✓ Docker уже установлен.${NC}"
fi

# Проверка Docker Compose (плагин compose или standalone)
DOCKER_COMPOSE=""
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${YELLOW}Устанавливаем Docker Compose плагин...${NC}"
    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1
        DOCKER_COMPOSE="docker compose"
    fi
fi

if [ -z "$DOCKER_COMPOSE" ]; then
    echo -e "${RED}❌ Не удалось настроить Docker Compose. Установите его вручную.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose готов к работе ($DOCKER_COMPOSE).${NC}"

# Создание необходимых папок
mkdir -p data backups
chmod 755 data backups

echo ""
echo -e "${CYAN}${BOLD}▶ [3/5] Настройка конфигурации бота (.env)${NC}"
echo -e "${YELLOW}Пожалуйста, ответьте на несколько вопросов для настройки бота:${NC}"
echo ""

# 1. Запрос BOT_TOKEN
CURRENT_TOKEN=""
if [ -f ".env" ]; then
    CURRENT_TOKEN=$(grep -E "^BOT_TOKEN=" .env | cut -d '=' -f2- | tr -d ' "' || true)
fi

while true; do
    if [ -n "$CURRENT_TOKEN" ]; then
        read -rp "1. Введите токен бота от @BotFather [текущий: $CURRENT_TOKEN]: " INPUT_TOKEN
        BOT_TOKEN="${INPUT_TOKEN:-$CURRENT_TOKEN}"
    else
        read -rp "1. Введите токен бота от @BotFather (например, 1234567890:ABC...): " BOT_TOKEN
    fi
    BOT_TOKEN=$(echo "$BOT_TOKEN" | xargs)
    if [ -n "$BOT_TOKEN" ]; then
        break
    fi
    echo -e "${RED}Токен не может быть пустым! Получите его в Telegram у бота @BotFather.${NC}"
done

# 2. Запрос ADMIN_IDS
CURRENT_ADMINS=""
if [ -f ".env" ]; then
    CURRENT_ADMINS=$(grep -E "^ADMIN_IDS=" .env | cut -d '=' -f2- | tr -d ' "' || true)
fi

while true; do
    echo ""
    echo -e "   ${CYAN}Подсказка:${NC} Узнать свой числовой ID можно в Telegram у бота @userinfobot"
    if [ -n "$CURRENT_ADMINS" ]; then
        read -rp "2. Введите Telegram ID администратора(ов) через запятую [текущий: $CURRENT_ADMINS]: " INPUT_ADMINS
        ADMIN_IDS="${INPUT_ADMINS:-$CURRENT_ADMINS}"
    else
        read -rp "2. Введите Telegram ID администратора(ов) через запятую (например, 123456789,987654321): " ADMIN_IDS
    fi
    ADMIN_IDS=$(echo "$ADMIN_IDS" | xargs | tr -d ' ')
    if [[ "$ADMIN_IDS" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        break
    fi
    echo -e "${RED}ID должны состоять только из цифр, разделенных запятыми!${NC}"
done

# 3. Запрос INITIAL_ALLOWED_USERS (whitelist)
CURRENT_ALLOWED=""
if [ -f ".env" ]; then
    CURRENT_ALLOWED=$(grep -E "^INITIAL_ALLOWED_USERS=" .env | cut -d '=' -f2- | tr -d ' "' || true)
fi

echo ""
echo -e "   ${CYAN}Белый список участников (Whitelist):${NC}"
echo -e "   ${GREEN}Не обязательно вводить сейчас!${NC} Участники смогут сами зайти в бота"
echo -e "   и нажать кнопку «📨 Подать заявку на участие», а вы одобрите их прямо в Telegram."
echo -e "   Также участников можно добавлять в любое время через админ-панель бота."
if [ -n "$CURRENT_ALLOWED" ]; then
    read -rp "3. Введите Telegram ID участников через запятую [Enter чтобы оставить $CURRENT_ALLOWED]: " INPUT_ALLOWED
    ALLOWED_USERS="${INPUT_ALLOWED:-$CURRENT_ALLOWED}"
else
    read -rp "3. Введите Telegram ID участников через запятую [Enter чтобы пропустить]: " INPUT_ALLOWED
    ALLOWED_USERS="${INPUT_ALLOWED:-$ADMIN_IDS}"
fi
ALLOWED_USERS=$(echo "$ALLOWED_USERS" | xargs | tr -d ' ')
if [ -z "$ALLOWED_USERS" ]; then
    ALLOWED_USERS="$ADMIN_IDS"
fi

# 4. Запрос GIFT_BUDGET
CURRENT_BUDGET=""
if [ -f ".env" ]; then
    CURRENT_BUDGET=$(grep -E "^GIFT_BUDGET=" .env | cut -d '=' -f2- | tr -d ' "' || true)
fi

echo ""
read -rp "4. Бюджет подарка в рублях [по умолчанию: ${CURRENT_BUDGET:-1000}]: " INPUT_BUDGET
GIFT_BUDGET="${INPUT_BUDGET:-${CURRENT_BUDGET:-1000}}"
GIFT_BUDGET=$(echo "$GIFT_BUDGET" | xargs)

# Запись в файл .env
cat <<EOF > .env
# Сгенерировано автоматическим установщиком $(date)
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
INITIAL_ALLOWED_USERS=$ALLOWED_USERS
GIFT_BUDGET=$GIFT_BUDGET
DB_PATH=data/database.json
BACKUP_DIR=backups
EOF

chmod 600 .env
echo -e "${GREEN}✓ Файл .env успешно сохранен!${NC}"

# Настройка скрипта управления и глобальной команды santa
echo ""
echo -e "${BLUE}▶ [4/5] Настройка панели управления...${NC}"
chmod +x manage.sh

# Создаем глобальную команду santa в /usr/local/bin
cat << EOF | $SUDO tee /usr/local/bin/santa >/dev/null
#!/usr/bin/env bash
exec bash "$SCRIPT_DIR/manage.sh" "\$@"
EOF
$SUDO chmod +x /usr/local/bin/santa
echo -e "${GREEN}✓ Глобальная команда ${BOLD}santa${NC}${GREEN} зарегистрирована в системе!${NC}"

# Сборка и запуск контейнера
echo ""
echo -e "${BLUE}▶ [5/5] Сборка и запуск бота в Docker...${NC}"
$DOCKER_COMPOSE down >/dev/null 2>&1 || true
$DOCKER_COMPOSE up -d --build

# Проверка статуса запуска
sleep 3
if [ -n "$($DOCKER_COMPOSE ps --status running -q 2>/dev/null)" ]; then
    echo ""
    echo -e "${GREEN}${BOLD}==========================================================${NC}"
    echo -e "${GREEN}${BOLD}        🎉 УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА! БОТ ЗАПУЩЕН!      ${NC}"
    echo -e "${GREEN}${BOLD}==========================================================${NC}"
    echo ""
    echo -e "• Для входа в панель управления введите в терминале команду:"
    echo -e "  ${CYAN}${BOLD}santa${NC}"
    echo ""
    echo -e "• Быстрые команды:"
    echo -e "  ${BOLD}santa status${NC}   - проверить состояние бота"
    echo -e "  ${BOLD}santa logs${NC}     - смотреть логи в реальном времени"
    echo -e "  ${BOLD}santa restart${NC}  - перезапустить бота"
    echo -e "  ${BOLD}santa stop${NC}     - остановить бота"
    echo -e "  ${BOLD}santa backup${NC}   - создать бэкап базы данных"
    echo -e "  ${BOLD}santa update${NC}   - скачать обновление с GitHub и перезапустить"
    echo ""
    echo -e "${YELLOW}База данных и бэкапы сохраняются в папках:${NC}"
    echo -e "  $SCRIPT_DIR/data/"
    echo -e "  $SCRIPT_DIR/backups/"
    echo ""
    read -rp "Открыть просмотр логов прямо сейчас? (Y/n): " show_logs
    if [[ ! "$show_logs" =~ ^[nNнН]$ ]]; then
        "$SCRIPT_DIR/manage.sh" logs
    fi
else
    echo -e "${RED}❌ Контейнер не запустился. Показываем последние логи:${NC}"
    $DOCKER_COMPOSE logs --tail=50
    echo ""
    echo -e "${YELLOW}Проверьте правильность токена бота в файле .env и повторите запуск: santa start${NC}"
fi
