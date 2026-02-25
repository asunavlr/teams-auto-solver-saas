"""
Configuracoes gerais do Teams Auto Solver SaaS.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INSTANCE_DIR = BASE_DIR / "instance"

DATA_DIR.mkdir(exist_ok=True)
INSTANCE_DIR.mkdir(exist_ok=True)

# Flask
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
DATABASE_URI = f"sqlite:///{INSTANCE_DIR / 'database.db'}"

# Admin
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Encriptacao de senhas dos clientes
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Scheduler
DEFAULT_CHECK_INTERVAL = int(os.getenv("DEFAULT_CHECK_INTERVAL", "60"))

# Logs
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Timezone (padrao: America/Sao_Paulo)
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

# UazAPI (WhatsApp)
UAZAPI_URL = os.getenv("UAZAPI_URL", "")
UAZAPI_TOKEN = os.getenv("UAZAPI_TOKEN", "")
ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP", "")  # Numero do admin para alertas
