"""
Teams Auto Solver SaaS - Entry Point
Inicia o painel web Flask + scheduler de monitoramento.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Configura logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger.add(LOG_DIR / "app.log", rotation="10 MB", retention="30 days")


def generate_encryption_key():
    """Gera chave de encriptacao se nao existir."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    print(f"\nChave de encriptacao gerada: {key}")
    print(f"Adicione ao seu .env: ENCRYPTION_KEY={key}\n")
    return key


def check_config():
    """Verifica configuracoes essenciais."""
    import config as cfg

    if cfg.SECRET_KEY == "change-me-in-production":
        logger.warning("SECRET_KEY nao configurada! Use uma chave segura no .env")

    if not cfg.ENCRYPTION_KEY:
        logger.error("ENCRYPTION_KEY nao configurada!")
        print("\nERRO: ENCRYPTION_KEY nao encontrada no .env")
        print("Execute: python app.py --generate-key")
        print("E adicione a chave gerada ao arquivo .env\n")
        sys.exit(1)

    if cfg.ADMIN_PASSWORD == "admin123":
        logger.warning("Senha admin padrao! Mude ADMIN_PASSWORD no .env")


def main():
    # Comandos especiais
    if "--generate-key" in sys.argv:
        generate_encryption_key()
        return

    check_config()

    # Cria app Flask
    from web import create_app
    app = create_app()

    # Inicia scheduler
    from engine.scheduler import init_scheduler
    init_scheduler(app)

    # Inicia servidor web
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    logger.info(f"Iniciando servidor em {host}:{port}")
    print(f"""
    =============================================
      TEAMS AUTO SOLVER - Painel Admin
    =============================================
      URL:    http://{host}:{port}
      Admin:  {os.getenv('ADMIN_USERNAME', 'admin')}
    =============================================
    """)

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    main()
