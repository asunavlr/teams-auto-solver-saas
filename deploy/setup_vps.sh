#!/bin/bash
# =============================================
# Teams Auto Solver SaaS - Setup VPS
# Testado em Ubuntu 22.04/24.04
# =============================================

set -e

APP_USER="solver"
APP_DIR="/opt/teams-auto-solver"
REPO_URL="https://github.com/asunavlr/teams-auto-solver-saas.git"

echo "============================================="
echo "  TEAMS AUTO SOLVER - Instalacao VPS"
echo "============================================="

# 1. Atualiza sistema
echo "[1/8] Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

# 2. Instala dependencias do sistema
echo "[2/8] Instalando dependencias..."
sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    git curl wget unzip \
    # Dependencias do Playwright/Chromium
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libxdamage1 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2

# 3. Cria usuario
echo "[3/8] Configurando usuario..."
if ! id "$APP_USER" &>/dev/null; then
    sudo useradd -m -s /bin/bash "$APP_USER"
fi

# 4. Clona repositorio
echo "[4/8] Clonando repositorio..."
sudo mkdir -p "$APP_DIR"
sudo chown "$APP_USER:$APP_USER" "$APP_DIR"

if [ -d "$APP_DIR/.git" ]; then
    sudo -u "$APP_USER" git -C "$APP_DIR" pull
else
    sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
fi

# 5. Configura ambiente Python
echo "[5/8] Configurando Python..."
cd "$APP_DIR"
sudo -u "$APP_USER" python3.11 -m venv venv
sudo -u "$APP_USER" bash -c "source venv/bin/activate && pip install -r requirements.txt"
sudo -u "$APP_USER" bash -c "source venv/bin/activate && playwright install chromium"

# 6. Configura .env
echo "[6/8] Configurando ambiente..."
if [ ! -f "$APP_DIR/.env" ]; then
    sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"

    # Gera chaves automaticamente
    SECRET=$(python3.11 -c "import secrets; print(secrets.token_hex(32))")
    ENC_KEY=$(sudo -u "$APP_USER" bash -c "source venv/bin/activate && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")

    sudo -u "$APP_USER" bash -c "cat > $APP_DIR/.env << EOF
SECRET_KEY=$SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD=MUDE_ESTA_SENHA
ENCRYPTION_KEY=$ENC_KEY
DEFAULT_CHECK_INTERVAL=60
HOST=0.0.0.0
PORT=5000
EOF"

    echo ""
    echo "  IMPORTANTE: Edite $APP_DIR/.env e mude ADMIN_PASSWORD!"
    echo ""
fi

# 7. Configura systemd
echo "[7/8] Configurando servico..."
sudo cp "$APP_DIR/deploy/teams-solver.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable teams-solver
sudo systemctl start teams-solver

# 8. Configura Nginx
echo "[8/8] Configurando Nginx..."
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/teams-solver
sudo ln -sf /etc/nginx/sites-available/teams-solver /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "============================================="
echo "  INSTALACAO CONCLUIDA!"
echo "============================================="
echo ""
echo "  Painel: http://$(curl -s ifconfig.me):80"
echo ""
echo "  Proximos passos:"
echo "  1. Edite /opt/teams-auto-solver/.env"
echo "     sudo nano /opt/teams-auto-solver/.env"
echo "  2. Mude ADMIN_PASSWORD"
echo "  3. Reinicie: sudo systemctl restart teams-solver"
echo "  4. (Opcional) Configure SSL:"
echo "     sudo certbot --nginx -d seudominio.com"
echo ""
echo "  Comandos uteis:"
echo "    sudo systemctl status teams-solver"
echo "    sudo journalctl -u teams-solver -f"
echo "    sudo systemctl restart teams-solver"
echo ""
