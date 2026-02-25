"""
Scheduler multi-cliente com APScheduler.
Gerencia jobs de monitoramento por cliente.
"""

import asyncio
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

# Scheduler global
scheduler = BackgroundScheduler()
_lock = threading.Lock()
_running_client = None  # Controle de execucao sequencial


def _get_app_context():
    """Obtem contexto do Flask para acessar o banco."""
    from web import create_app
    app = create_app()
    return app.app_context()


def _build_client_config(client):
    """Constroi ClientConfig a partir do modelo do banco."""
    from engine.monitor import ClientConfig
    return ClientConfig(
        client_id=client.id,
        nome=client.nome,
        teams_email=client.teams_email,
        teams_password=client.teams_password,
        anthropic_key=client.anthropic_key,
        data_dir=client.data_dir,
        check_interval=client.check_interval,
        smtp_email=client.smtp_email,
        smtp_password=client.smtp_password,
        notification_email=client.notification_email,
    )


def _run_client_sync(client_id: int):
    """Executa o ciclo de monitoramento para um cliente (sync wrapper)."""
    global _running_client

    with _lock:
        if _running_client is not None:
            logger.info(f"Cliente {_running_client} em execucao, adiando cliente {client_id}")
            return
        _running_client = client_id

    try:
        # Importa dentro da funcao para evitar circular
        from web import db, create_app
        from web.models import Client, TaskLog
        from engine.monitor import ciclo_monitoramento_cliente

        app = create_app()
        with app.app_context():
            client = db.session.get(Client, client_id)
            if not client:
                logger.error(f"Cliente {client_id} nao encontrado")
                return

            if not client.is_active:
                logger.info(f"Cliente {client.nome} nao esta ativo, removendo job")
                remove_client_job(client_id)
                if client.is_expired:
                    client.status = "expired"
                    db.session.commit()
                return

            config = _build_client_config(client)

            # Executa o ciclo async
            loop = asyncio.new_event_loop()
            try:
                resultado = loop.run_until_complete(ciclo_monitoramento_cliente(config))
            finally:
                loop.close()

            # Atualiza banco com resultados
            client.last_check = datetime.utcnow()

            for task in resultado.get("tasks", []):
                task_log = TaskLog(
                    client_id=client_id,
                    task_name=task.get("name", ""),
                    discipline=task.get("discipline", ""),
                    format=task.get("format", ""),
                    status=task.get("status", "error"),
                    error_msg=task.get("error", ""),
                )
                db.session.add(task_log)
                if task.get("status") == "success":
                    client.tasks_completed += 1

            db.session.commit()
            logger.info(f"Cliente {client.nome}: ciclo concluido")

    except Exception as e:
        logger.error(f"Erro no job do cliente {client_id}: {e}")
    finally:
        with _lock:
            _running_client = None


def add_client_job(client_id: int):
    """Adiciona ou atualiza job de um cliente no scheduler."""
    job_id = f"client_{client_id}"

    # Remove job existente se houver
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    # Busca intervalo do cliente
    try:
        from web import db, create_app
        from web.models import Client

        app = create_app()
        with app.app_context():
            client = db.session.get(Client, client_id)
            if not client or not client.is_active:
                return
            interval = client.check_interval
    except Exception:
        interval = 60

    scheduler.add_job(
        _run_client_sync,
        trigger=IntervalTrigger(minutes=interval),
        args=[client_id],
        id=job_id,
        name=f"Monitor cliente {client_id}",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Job adicionado: cliente {client_id} (cada {interval} min)")


def remove_client_job(client_id: int):
    """Remove job de um cliente."""
    job_id = f"client_{client_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Job removido: cliente {client_id}")


def run_client_now(client_id: int):
    """Executa o monitoramento de um cliente imediatamente."""
    thread = threading.Thread(target=_run_client_sync, args=[client_id], daemon=True)
    thread.start()
    logger.info(f"Execucao imediata iniciada: cliente {client_id}")


def init_scheduler(app):
    """Inicializa o scheduler e carrega todos os clientes ativos."""
    if scheduler.running:
        return

    with app.app_context():
        from web.models import Client
        from web import db

        active_clients = Client.query.filter_by(status="active").all()
        active_clients = [c for c in active_clients if c.is_active]

        for client in active_clients:
            job_id = f"client_{client.id}"
            scheduler.add_job(
                _run_client_sync,
                trigger=IntervalTrigger(minutes=client.check_interval),
                args=[client.id],
                id=job_id,
                name=f"Monitor cliente {client.id}",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(f"Job carregado: {client.nome} (cada {client.check_interval} min)")

    scheduler.start()
    logger.info(f"Scheduler iniciado com {len(active_clients)} cliente(s) ativo(s)")
