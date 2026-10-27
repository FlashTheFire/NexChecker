#!/usr/bin/env bash
# ==============================================================================
# NexChecker Universal Deployment & Management Engine
# Supports: Any Linux OS (Ubuntu, Debian, CentOS, RHEL, Fedora, Rocky, Alma, Arch, Alpine)
# Cloud / VPS: AWS, GCP, Azure, DigitalOcean, Hetzner, Linode, On-Prem, Local
# Modes: Docker Compose (Default) / Native Systemd Service / Standalone
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${APP_DIR}"

MODE="docker"
ACTION="deploy"
PORT="${PORT:-8000}"
CURRENT_USER="$(id -un)"

# ── Color Output Helpers ──────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}ℹ️  [NexChecker]${NC} $1"; }
log_ok()    { echo -e "${GREEN}✅ [NexChecker]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠️  [NexChecker]${NC} $1"; }
log_err()   { echo -e "${RED}❌ [NexChecker]${NC} $1"; }

# ── Parse Arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker)
            MODE="docker"
            shift
            ;;
        --native|--systemd)
            MODE="native"
            shift
            ;;
        --setup-only)
            ACTION="setup"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --restart)
            ACTION="restart"
            shift
            ;;
        --stop)
            ACTION="stop"
            shift
            ;;
        --logs)
            ACTION="logs"
            shift
            ;;
        --help|-h)
            echo "NexChecker Universal Deployment Engine"
            echo ""
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --docker       Deploy via Docker Compose (Default, Recommended)"
            echo "  --native       Deploy natively via Python virtual environment & Systemd"
            echo "  --setup-only   Only install system dependencies, swap, and certs"
            echo "  --status       Check status of running services"
            echo "  --restart      Restart running services"
            echo "  --stop         Stop all running services"
            echo "  --logs         Tail live application and bot logs"
            echo "  --help, -h     Show this help message"
            exit 0
            ;;
        *)
            log_warn "Unknown parameter: $1 (ignoring)"
            shift
            ;;
    esac
done

echo -e "${CYAN}======================================================================${NC}"
echo -e "${GREEN}🚀 NexChecker Universal Deployment Engine${NC}"
echo -e "   Target Directory: ${APP_DIR}"
echo -e "   Deployment Mode:  ${MODE^^}"
echo -e "   Action:           ${ACTION^^}"
echo -e "${CYAN}======================================================================${NC}"

# ── Function: OS & Package Manager Detection ──────────────────────────────────
detect_os() {
    OS_NAME="unknown"
    PKG_MGR="unknown"

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_NAME="${ID:-linux}"
    fi

    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
    elif command -v pacman &>/dev/null; then
        PKG_MGR="pacman"
    elif command -v apk &>/dev/null; then
        PKG_MGR="apk"
    fi

    log_info "Detected OS: ${OS_NAME} (Package Manager: ${PKG_MGR})"
}

# ── Function: Configure Swap for Low-Memory Systems ───────────────────────────
configure_swap() {
    # Check total RAM in MB
    if [ -f /proc/meminfo ]; then
        TOTAL_RAM=$(grep MemTotal /proc/meminfo | awk '{print int($2/1024)}')
        SWAP_TOTAL=$(grep SwapTotal /proc/meminfo | awk '{print int($2/1024)}')

        if [ "${TOTAL_RAM}" -lt 2000 ] && [ "${SWAP_TOTAL}" -lt 1000 ]; then
            log_warn "System RAM is ${TOTAL_RAM}MB with low swap (${SWAP_TOTAL}MB). Configuring 2GB swap..."
            if [ "$(id -u)" -eq 0 ] || command -v sudo &>/dev/null; then
                SUDO_CMD=""
                [ "$(id -u)" -ne 0 ] && SUDO_CMD="sudo"
                
                if ! grep -q "swapfile" /etc/fstab 2>/dev/null; then
                    ${SUDO_CMD} fallocate -l 2G /swapfile 2>/dev/null || ${SUDO_CMD} dd if=/dev/zero of=/swapfile bs=1M count=2048
                    ${SUDO_CMD} chmod 600 /swapfile
                    ${SUDO_CMD} mkswap /swapfile
                    ${SUDO_CMD} swapon /swapfile || true
                    echo '/swapfile none swap sw 0 0' | ${SUDO_CMD} tee -a /etc/fstab >/dev/null
                    ${SUDO_CMD} sysctl vm.swappiness=10 || true
                    echo 'vm.swappiness=10' | ${SUDO_CMD} tee -a /etc/sysctl.conf >/dev/null
                    log_ok "2GB swap configured successfully."
                fi
            else
                log_warn "Non-root user without sudo: unable to configure swap automatically."
            fi
        fi
    fi
}

# ── Function: Prepare Storage & Environment ───────────────────────────────────
prepare_environment() {
    log_info "Verifying environment and storage directories..."

    # 1. Environment file
    if [ ! -f "${APP_DIR}/.env" ]; then
        if [ -f "${APP_DIR}/.env.example" ]; then
            log_warn ".env not found. Initializing from .env.example..."
            cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
            log_ok "Created .env. Please update BOT_TOKEN and credentials as needed."
        else
            log_err "Neither .env nor .env.example found in ${APP_DIR}!"
            exit 1
        fi
    fi

    # 2. Hierarchical JSON storage directories
    mkdir -p "${APP_DIR}/NexBot/data/users"
    chmod -R 775 "${APP_DIR}/NexBot/data" 2>/dev/null || true

    # 3. SSL certificates for reverse proxy
    CERT_DIR="${APP_DIR}/docker/certs"
    mkdir -p "${CERT_DIR}"
    if [ ! -f "${CERT_DIR}/cert.pem" ] || [ ! -f "${CERT_DIR}/key.pem" ]; then
        log_info "Generating self-signed SSL certificates for reverse proxy..."
        if command -v openssl &>/dev/null; then
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout "${CERT_DIR}/key.pem" \
                -out "${CERT_DIR}/cert.pem" \
                -subj "/C=IN/ST=Delhi/L=Universal/O=NexChecker/CN=nexchecker.local" \
                -addext "subjectAltName=DNS:localhost,DNS:*.nip.io,IP:127.0.0.1" 2>/dev/null || \
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout "${CERT_DIR}/key.pem" \
                -out "${CERT_DIR}/cert.pem" \
                -subj "/C=IN/ST=Delhi/L=Universal/O=NexChecker/CN=nexchecker.local"
            log_ok "SSL certificates generated."
        else
            log_warn "OpenSSL not found. Reverse proxy will require manual certificates."
        fi
    fi
}

# ── Function: Install Docker & Compose (Universal) ────────────────────────────
ensure_docker() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null; then
        log_ok "Docker and Docker Compose plugin are ready."
        return 0
    fi

    log_warn "Docker or Docker Compose is missing. Attempting automated installation..."
    SUDO_CMD=""
    [ "$(id -u)" -ne 0 ] && SUDO_CMD="sudo"

    case "${PKG_MGR}" in
        apt)
            ${SUDO_CMD} apt-get update -y
            ${SUDO_CMD} apt-get install -y ca-certificates curl gnupg lsb-release
            ${SUDO_CMD} install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/ubuntu/gpg | ${SUDO_CMD} gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes 2>/dev/null || true
            ${SUDO_CMD} chmod a+r /etc/apt/keyrings/docker.gpg 2>/dev/null || true
            
            UBUNTU_CODENAME="$(lsb_release -cs 2>/dev/null || echo 'jammy')"
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" | \
                ${SUDO_CMD} tee /etc/apt/sources.list.d/docker.list > /dev/null
            
            ${SUDO_CMD} apt-get update -y || true
            ${SUDO_CMD} apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || \
            ${SUDO_CMD} apt-get install -y docker.io docker-compose
            ;;
        dnf|yum)
            ${SUDO_CMD} ${PKG_MGR} install -y yum-utils
            ${SUDO_CMD} yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            ${SUDO_CMD} ${PKG_MGR} install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        pacman)
            ${SUDO_CMD} pacman -Sy --noconfirm docker docker-compose
            ;;
        apk)
            ${SUDO_CMD} apk add --no-cache docker docker-compose
            ;;
        *)
            log_warn "Unknown package manager. Trying universal convenience script from get.docker.com..."
            curl -fsSL https://get.docker.com | ${SUDO_CMD} sh
            ;;
    esac

    # Add user to docker group & start service
    if command -v systemctl &>/dev/null; then
        ${SUDO_CMD} systemctl enable docker || true
        ${SUDO_CMD} systemctl start docker || true
    fi
    ${SUDO_CMD} usermod -aG docker "${CURRENT_USER}" 2>/dev/null || true

    log_ok "Docker engine installed."
}

# ── Function: Deploy Docker Mode ──────────────────────────────────────────────
deploy_docker() {
    ensure_docker
    log_info "Building and launching containers via Docker Compose..."
    
    # Check if docker commands require sudo
    DOCKER_CMD="docker"
    if ! docker info &>/dev/null; then
        if sudo docker info &>/dev/null; then
            DOCKER_CMD="sudo docker"
        fi
    fi

    ${DOCKER_CMD} compose down --remove-orphans 2>/dev/null || true
    ${DOCKER_CMD} compose build --pull
    ${DOCKER_CMD} compose up -d

    log_ok "Docker services started."
    sleep 3
    ${DOCKER_CMD} compose ps
}

# ── Function: Deploy Native Systemd Mode ───────────────────────────────────────
deploy_native() {
    log_info "Configuring Native Host Execution..."

    SUDO_CMD=""
    [ "$(id -u)" -ne 0 ] && SUDO_CMD="sudo"

    # Install Python3, pip, venv if missing
    if ! command -v python3 &>/dev/null; then
        log_warn "Python3 missing. Installing..."
        case "${PKG_MGR}" in
            apt) ${SUDO_CMD} apt-get update -y && ${SUDO_CMD} apt-get install -y python3 python3-pip python3-venv ;;
            dnf|yum) ${SUDO_CMD} ${PKG_MGR} install -y python3 python3-pip ;;
            pacman) ${SUDO_CMD} pacman -Sy --noconfirm python python-pip ;;
            apk) ${SUDO_CMD} apk add --no-cache python3 py3-pip ;;
        esac
    fi

    VENV_DIR="${APP_DIR}/venv"
    if [ ! -d "${VENV_DIR}" ]; then
        log_info "Creating virtual environment at ${VENV_DIR}..."
        python3 -m venv "${VENV_DIR}"
    fi

    PYTHON_BIN="${VENV_DIR}/bin/python"
    PIP_BIN="${VENV_DIR}/bin/pip"
    UVICORN_BIN="${VENV_DIR}/bin/uvicorn"

    log_info "Installing dependencies from requirements.txt..."
    "${PIP_BIN}" install --upgrade pip
    "${PIP_BIN}" install -r "${APP_DIR}/requirements.txt"

    # Install Playwright Chromium & system libraries
    log_info "Installing Playwright Chromium dependencies..."
    "${VENV_DIR}/bin/playwright" install --with-deps chromium || true

    # Configure Systemd Services if systemd is available
    if command -v systemctl &>/dev/null; then
        log_info "Configuring universal systemd service units..."
        
        BOT_TMPL="${APP_DIR}/deploy/systemd/nexchecker-bot.service.template"
        API_TMPL="${APP_DIR}/deploy/systemd/nexchecker-api.service.template"

        BOT_SERVICE="/etc/systemd/system/nexchecker-bot.service"
        API_SERVICE="/etc/systemd/system/nexchecker-api.service"

        sed \
            -e "s|{{SERVICE_USER}}|${CURRENT_USER}|g" \
            -e "s|{{APP_DIR}}|${APP_DIR}|g" \
            -e "s|{{PYTHON_BIN}}|${PYTHON_BIN}|g" \
            "${BOT_TMPL}" | ${SUDO_CMD} tee "${BOT_SERVICE}" >/dev/null

        sed \
            -e "s|{{SERVICE_USER}}|${CURRENT_USER}|g" \
            -e "s|{{APP_DIR}}|${APP_DIR}|g" \
            -e "s|{{UVICORN_BIN}}|${UVICORN_BIN}|g" \
            -e "s|{{API_PORT}}|${PORT}|g" \
            "${API_TMPL}" | ${SUDO_CMD} tee "${API_SERVICE}" >/dev/null

        ${SUDO_CMD} systemctl daemon-reload
        ${SUDO_CMD} systemctl enable --now nexchecker-api
        ${SUDO_CMD} systemctl enable --now nexchecker-bot

        log_ok "Systemd services nexchecker-api and nexchecker-bot are active."
    else
        log_warn "Systemd not detected (containerized or non-systemd init). You can run manually via:"
        echo "  ${PYTHON_BIN} NexBot/bot.py &"
        echo "  ${UVICORN_BIN} api.main:app --host 0.0.0.0 --port ${PORT} &"
    fi
}

# ── Function: Actions (status, restart, stop, logs) ───────────────────────────
handle_actions() {
    DOCKER_CMD="docker"
    if ! docker info &>/dev/null 2>&1; then
        if command -v sudo &>/dev/null && sudo docker info &>/dev/null 2>&1; then
            DOCKER_CMD="sudo docker"
        fi
    fi

    case "${ACTION}" in
        status)
            echo -e "${CYAN}--- Docker Service Status ---${NC}"
            ${DOCKER_CMD} compose ps 2>/dev/null || echo "No docker compose active."
            if command -v systemctl &>/dev/null; then
                echo -e "${CYAN}--- Systemd Service Status ---${NC}"
                systemctl status nexchecker-bot --no-pager 2>/dev/null || true
                systemctl status nexchecker-api --no-pager 2>/dev/null || true
            fi
            exit 0
            ;;
        restart)
            log_info "Restarting services..."
            ${DOCKER_CMD} compose restart 2>/dev/null || true
            if command -v systemctl &>/dev/null; then
                sudo systemctl restart nexchecker-bot 2>/dev/null || true
                sudo systemctl restart nexchecker-api 2>/dev/null || true
            fi
            log_ok "Restart complete."
            exit 0
            ;;
        stop)
            log_info "Stopping services..."
            ${DOCKER_CMD} compose down 2>/dev/null || true
            if command -v systemctl &>/dev/null; then
                sudo systemctl stop nexchecker-bot 2>/dev/null || true
                sudo systemctl stop nexchecker-api 2>/dev/null || true
            fi
            log_ok "Services stopped."
            exit 0
            ;;
        logs)
            if ${DOCKER_CMD} compose ps -q bot &>/dev/null; then
                ${DOCKER_CMD} compose logs -f bot api
            elif command -v journalctl &>/dev/null; then
                sudo journalctl -u nexchecker-bot -f
            else
                log_warn "No running service logs found."
            fi
            exit 0
            ;;
        *)
            ;;
    esac
}

# ── Main Flow ─────────────────────────────────────────────────────────────────
detect_os
configure_swap
prepare_environment
handle_actions

if [ "${ACTION}" = "setup" ]; then
    if [ "${MODE}" = "docker" ]; then
        ensure_docker
    else
        deploy_native
    fi
    log_ok "Setup completed successfully."
    exit 0
fi

if [ "${MODE}" = "docker" ]; then
    deploy_docker
else
    deploy_native
fi

echo -e "${CYAN}======================================================================${NC}"
echo -e "${GREEN}🎉 NexChecker is LIVE and Operational!${NC}"
echo -e "   Health Check:     http://localhost:${PORT}/api/health"
echo -e "   API Docs:         http://localhost:${PORT}/docs"
echo -e "   View Live Logs:   ./deploy.sh --logs"
echo -e "   Service Status:   ./deploy.sh --status"
echo -e "${CYAN}======================================================================${NC}"
