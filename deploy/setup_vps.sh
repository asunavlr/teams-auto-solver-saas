#!/bin/bash
# =============================================
# Teams Auto Solver SaaS - Setup VPS (Docker)
# Testado em Ubuntu 22.04/24.04
# =============================================

set -e

APP_DIR="/opt/teams-auto-solver"
REPO_URL="https://github.com/asunavlr/teams-auto-solver-saas.git"

echo "============================================="
echo "  TEAMS AUTO SOLVER - Instalacao VPS"
echo "============================================="

# 1. Atualiza sistema
echo "[1/6] Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

# 2. Instala Docker
echo "[2/6] Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "Docker instalado. Pode ser necessario relogar para usar sem sudo."
fi

# 3. Instala Nginx + Certbot
echo "[3/6] Instalando Nginx..."
sudo apt install -y nginx certbot python3-certbot-nginx

# 4. Clona repositorio
echo "[4/6] Clonando repositorio..."
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
fi

# 5. Configura .env
echo "[5/6] Configurando ambiente..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"

    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "GERE_UMA_CHAVE_FERNET")

    cat > "$APP_DIR/.env" << EOF
SECRET_KEY=$SECRET
JWT_SECRET_KEY=$JWT_SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD=MUDE_ESTA_SENHA
ENCRYPTION_KEY=$ENC_KEY
DEFAULT_CHECK_INTERVAL=60
HOST=0.0.0.0
PORT=5000
TIMEZONE=America/Sao_Paulo
DATABASE_URI=sqlite:///instance/database.db
EOF

    echo ""
    echo "  IMPORTANTE: Edite $APP_DIR/.env"
    echo "  - Mude ADMIN_PASSWORD"
    echo "  - Configure DATABASE_URI (Supabase)"
    echo ""
fi

# 6. Sobe os containers
echo "[6/6] Iniciando containers..."
cd "$APP_DIR"
docker compose up -d --build

# Configura Nginx
echo "Configurando Nginx..."
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
echo "     nano /opt/teams-auto-solver/.env"
echo "  2. Mude ADMIN_PASSWORD e configure DATABASE_URI"
echo "  3. Reinicie: cd /opt/teams-auto-solver && docker compose up -d"
echo "  4. (Opcional) Configure SSL:"
echo "     sudo certbot --nginx -d seudominio.com"
echo ""
echo "  Comandos uteis:"
echo "    docker compose ps"
echo "    docker compose logs -f app"
echo "    docker compose restart"
echo "    docker compose down && docker compose up -d --build"
echo ""
