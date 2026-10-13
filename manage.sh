#!/usr/bin/env bash

# ==============================================================================
# Панель управления ботом «Тайный Санта»
# Использование:
#   ./manage.sh            - интерактивное меню
#   ./manage.sh status     - статус бота
#   ./manage.sh start      - запуск бота
#   ./manage.sh stop       - остановка бота
#   ./manage.sh restart    - перезапуск бота
#   ./manage.sh logs       - просмотр логов
#   ./manage.sh backup     - создать бэкап БД
#   ./manage.sh restore    - восстановить БД из бэкапа
#   ./manage.sh update     - обновить из репозитория GitHub
# ==============================================================================

# Определение директории проекта (с надежным разрешением всех симлинков)
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

# Определение команды docker compose
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose --project-directory $SCRIPT_DIR -f $COMPOSE_FILE"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose --project-directory $SCRIPT_DIR -f $COMPOSE_FILE"
else
    echo -e "${RED}❌ Docker Compose не найден! Убедитесь, что Docker установлен.${NC}"
    exit 1
fi

get_container_status() {
    local status
    status=$($DOCKER_COMPOSE ps --status running -q 2>/dev/null)
    if [ -n "$status" ]; then
        echo "running"
    else
        echo "stopped"
    fi
}

show_header() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "=========================================================="
    echo "       🎅 ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ «ТАЙНЫЙ САНТА»          "
    echo "=========================================================="
    echo -e "${NC}"
}

cmd_status() {
    echo -e "${BOLD}--- Статус бота ---${NC}"
    local status
    status=$(get_container_status)
    if [ "$status" = "running" ]; then
        echo -e "Состояние: ${GREEN}🟢 РАБОТАЕТ (Running)${NC}\n"
        $DOCKER_COMPOSE ps
        echo ""
        echo -e "${CYAN}Использование ресурсов:${NC}"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>/dev/null | grep -E "secret_santa|NAME"
    else
        echo -e "Состояние: ${RED}🔴 ОСТАНОВЛЕН (Stopped)${NC}\n"
    fi

    if [ -f "data/database.json" ]; then
        echo ""
        echo -e "${YELLOW}База данных:${NC}"
        python3 -c "
import json
try:
    with open('data/database.json', 'r', encoding='utf-8') as f:
        d = json.load(f)
    users = len(d.get('users', {}))
    allowed = len(d.get('allowed_users', []))
    total = d.get('settings', {}).get('total_participants', '?')
    dist = 'Да' if d.get('auto_distribution_done') else 'Нет'
    deadline = d.get('settings', {}).get('registration_deadline', 'по умолчанию')
    print(f'• Зарегистрировано участников: {users}/{total}')
    print(f'• В списке доступа (whitelist): {allowed}')
    print(f'• Распределение завершено: {dist}')
    print(f'• Дедлайн регистрации: {deadline}')
except Exception as e:
    print('• Ошибка чтения данных:', e)
" 2>/dev/null
    fi
    echo ""
}

cmd_start() {
    echo -e "${YELLOW}🚀 Запуск контейнера бота...${NC}"
    $DOCKER_COMPOSE up -d
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Бот успешно запущен!${NC}"
    else
        echo -e "${RED}❌ Ошибка запуска бота.${NC}"
    fi
}

cmd_stop() {
    echo -e "${YELLOW}⏹️ Остановка контейнера бота...${NC}"
    $DOCKER_COMPOSE down
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Бот успешно остановлен!${NC}"
    else
        echo -e "${RED}❌ Ошибка остановки бота.${NC}"
    fi
}

cmd_restart() {
    echo -e "${YELLOW}🔄 Перезапуск бота...${NC}"
    $DOCKER_COMPOSE restart
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Бот успешно перезапущен!${NC}"
    else
        echo -e "${RED}❌ Ошибка перезапуска. Пробуем пересоздать...${NC}"
        $DOCKER_COMPOSE down && $DOCKER_COMPOSE up -d
    fi
}

cmd_logs() {
    echo -e "${CYAN}📜 Просмотр логов в реальном времени (Ctrl+C для выхода):${NC}"
    echo "----------------------------------------------------------"
    $DOCKER_COMPOSE logs -f --tail=100
}

cmd_backup() {
    mkdir -p "$SCRIPT_DIR/backups"
    if [ ! -f "$SCRIPT_DIR/data/database.json" ]; then
        echo -e "${YELLOW}⚠️ Файл базы данных ($SCRIPT_DIR/data/database.json) пока не создан.${NC}"
        return
    fi
    local ts
    ts=$(date +"%Y%m%d_%H%M%S")
    local backup_file="$SCRIPT_DIR/backups/manual_backup_${ts}.json"
    cp "$SCRIPT_DIR/data/database.json" "$backup_file"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Резервная копия успешно создана:${NC} ${backup_file}"
    else
        echo -e "${RED}❌ Ошибка при создании резервной копии.${NC}"
    fi
}

cmd_restore() {
    mkdir -p "$SCRIPT_DIR/backups"
    local backups=("$SCRIPT_DIR/backups"/*.json)
    if [ ! -e "${backups[0]}" ]; then
        echo -e "${RED}❌ В папке $SCRIPT_DIR/backups/ нет сохраненных резервных копий.${NC}"
        return
    fi

    echo -e "${CYAN}Доступные резервные копии:${NC}"
    local i=1
    for b in "${backups[@]}"; do
        echo -e "  ${BOLD}$i)${NC} $(basename "$b") ($(stat -c%y "$b" 2>/dev/null || date -r "$b"))"
        ((i++))
    done

    echo ""
    read -rp "Выберите номер копии для восстановления (или 0 для отмены): " choice
    if [[ ! "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -le 0 ] || [ "$choice" -ge "$i" ]; then
        echo -e "${YELLOW}Отмена восстановления.${NC}"
        return
    fi

    local selected_backup="${backups[$((choice - 1))]}"
    echo -e "${YELLOW}⚠️ Выбрана копия: $selected_backup${NC}"
    read -rp "Вы уверены, что хотите восстановить эту копию? Текущие данные будут заменены (y/N): " confirm
    if [[ "$confirm" =~ ^[yYдД]$ ]]; then
        # Делаем резервную копию текущего состояния перед откатом
        if [ -f "$SCRIPT_DIR/data/database.json" ]; then
            cp "$SCRIPT_DIR/data/database.json" "$SCRIPT_DIR/backups/pre_restore_backup_$(date +"%Y%m%d_%H%M%S").json"
        fi
        cp "$selected_backup" "$SCRIPT_DIR/data/database.json"
        echo -e "${GREEN}✅ База данных восстановлена из $selected_backup!${NC}"
        echo -e "${YELLOW}Перезапускаем бота для применения изменений...${NC}"
        cmd_restart
    else
        echo -e "${YELLOW}Восстановление отменено.${NC}"
    fi
}

cmd_edit_env() {
    local editor="${EDITOR:-nano}"
    if ! command -v "$editor" >/dev/null 2>&1; then
        editor="vi"
    fi
    echo -e "${YELLOW}Открываем файл $SCRIPT_DIR/.env в редакторе $editor...${NC}"
    $editor "$SCRIPT_DIR/.env"
    read -rp "Перезапустить бота для применения новых настроек? (y/N): " restart_confirm
    if [[ "$restart_confirm" =~ ^[yYдД]$ ]]; then
        cmd_restart
    fi
}

cmd_update() {
    echo -e "${CYAN}🚀 Обновление бота из GitHub...${NC}"
    if [ ! -d "$SCRIPT_DIR/.git" ]; then
        echo -e "${RED}❌ Папка $SCRIPT_DIR не является git-репозиторием.${NC}"
        return
    fi

    echo -e "${YELLOW}1. Получение последних изменений (git pull)...${NC}"
    (cd "$SCRIPT_DIR" && git pull)
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Ошибка при выполнении git pull.${NC}"
        return
    fi

    echo -e "${YELLOW}2. Пересборка Docker-образа и перезапуск...${NC}"
    $DOCKER_COMPOSE up -d --build
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Бот успешно обновлен и перезапущен!${NC}"
    else
        echo -e "${RED}❌ Ошибка при сборке контейнера.${NC}"
    fi
}

interactive_menu() {
    while true; do
        show_header
        local status
        status=$(get_container_status)
        if [ "$status" = "running" ]; then
            echo -e "  Статус: ${GREEN}🟢 РАБОТАЕТ${NC}\n"
        else
            echo -e "  Статус: ${RED}🔴 ОСТАНОВЛЕН${NC}\n"
        fi

        echo -e "  ${BOLD}1)${NC} 📊 Подробный статус и статистика"
        echo -e "  ${BOLD}2)${NC} ▶️  Запустить бота"
        echo -e "  ${BOLD}3)${NC} ⏹️  Остановить бота"
        echo -e "  ${BOLD}4)${NC} 🔄 Перезапустить бота"
        echo -e "  ${BOLD}5)${NC} 📜 Просмотр логов (live logs)"
        echo -e "  ${BOLD}6)${NC} ⚙️  Редактировать настройки (.env)"
        echo -e "  ${BOLD}7)${NC} 💾 Создать резервную копию базы данных (бэкап)"
        echo -e "  ${BOLD}8)${NC} 📂 Восстановить базу данных из бэкапа"
        echo -e "  ${BOLD}9)${NC} 🚀 Обновить бота с GitHub (pull & rebuild)"
        echo -e "  ${BOLD}0)${NC} 🚪 Выход"
        echo ""
        read -rp "Выберите действие [0-9]: " choice

        case "$choice" in
            1)
                clear
                cmd_status
                read -rp "Нажмите Enter для возврата в меню..."
                ;;
            2)
                cmd_start
                sleep 2
                ;;
            3)
                cmd_stop
                sleep 2
                ;;
            4)
                cmd_restart
                sleep 2
                ;;
            5)
                cmd_logs
                ;;
            6)
                cmd_edit_env
                ;;
            7)
                cmd_backup
                sleep 2
                ;;
            8)
                cmd_restore
                read -rp "Нажмите Enter для продолжения..."
                ;;
            9)
                cmd_update
                read -rp "Нажмите Enter для продолжения..."
                ;;
            0|q|Q)
                echo -e "${GREEN}До свидания! 🎅${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Неверный ввод!${NC}"
                sleep 1
                ;;
        esac
    done
}

# Обработка аргументов командной строки
case "$1" in
    status)
        cmd_status
        ;;
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs
        ;;
    backup)
        cmd_backup
        ;;
    restore)
        cmd_restore
        ;;
    edit-env|env)
        cmd_edit_env
        ;;
    update)
        cmd_update
        ;;
    help|--help|-h)
        echo "Использование: $0 [status|start|stop|restart|logs|backup|restore|env|update]"
        ;;
    "")
        interactive_menu
        ;;
    *)
        echo -e "${RED}Неизвестная команда: $1${NC}"
        echo "Использование: $0 [status|start|stop|restart|logs|backup|restore|env|update]"
        exit 1
        ;;
esac
