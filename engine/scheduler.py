"""
Scheduler multi-cliente com APScheduler.
Gerencia jobs de monitoramento por cliente.
"""

import asyncio
import threading
import queue
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

# Scheduler global
scheduler = BackgroundScheduler()
_lock = threading.Lock()
_running_client = None
_pending_queue = queue.Queue()  # Fila de clientes aguardando execucao
_queue_processor_running = False


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


def _process_queue():
    """Processa a fila de clientes pendentes."""
    global _queue_processor_running

    while True:
        try:
            # Espera ate ter item na fila (timeout de 5s para checar se deve parar)
            try:
                client_id = _pending_queue.get(timeout=5)
            except queue.Empty:
                # Verifica se ainda tem trabalho
                with _lock:
                    if _pending_queue.empty() and _running_client is None:
                        _queue_processor_running = False
                        return
                continue

            # Executa o cliente
            _execute_client(client_id)
            _pending_queue.task_done()

        except Exception as e:
            logger.error(f"Erro no processador de fila: {e}")


def _ensure_queue_processor():
    """Garante que o processador de fila esta rodando."""
    global _queue_processor_running

    with _lock:
        if not _queue_processor_running:
            _queue_processor_running = True
            thread = threading.Thread(target=_process_queue, daemon=True)
            thread.start()


def _execute_client(client_id: int):
    """Executa o ciclo de monitoramento para um cliente."""
    global _running_client

    # Marca como em execucao
    with _lock:
        _running_client = client_id

    try:
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


def _run_client_sync(client_id: int):
    """Agenda execucao de um cliente (adiciona na fila se necessario)."""
    global _running_client

    with _lock:
        if _running_client is not None:
            # Verifica se ja esta na fila para evitar duplicatas
            pending_list = list(_pending_queue.queue)
            if client_id not in pending_list:
                _pending_queue.put(client_id)
                logger.info(f"Cliente {client_id} adicionado na fila (aguardando {_running_client})")
            else:
                logger.debug(f"Cliente {client_id} ja esta na fila, ignorando")
            _ensure_queue_processor()
            return

    # Nenhum cliente rodando, executa direto
    _ensure_queue_processor()
    _pending_queue.put(client_id)


def add_client_job(client_id: int, run_now: bool = False):
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
            client_nome = client.nome
    except Exception:
        interval = 60
        client_nome = f"ID {client_id}"

    scheduler.add_job(
        _run_client_sync,
        trigger=IntervalTrigger(minutes=interval),
        args=[client_id],
        id=job_id,
        name=f"Monitor cliente {client_id}",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Job adicionado: {client_nome} (cada {interval} min)")

    # Executa primeira vez imediatamente se solicitado
    if run_now:
        run_client_now(client_id)


def remove_client_job(client_id: int):
    """Remove job de um cliente."""
    job_id = f"client_{client_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Job removido: cliente {client_id}")


def run_client_now(client_id: int):
    """Executa o monitoramento de um cliente imediatamente."""
    _pending_queue.put(client_id)
    _ensure_queue_processor()
    logger.info(f"Execucao imediata agendada: cliente {client_id}")


def get_queue_status():
    """Retorna status da fila de execucao."""
    with _lock:
        return {
            "running_client": _running_client,
            "pending_count": _pending_queue.qsize(),
            "pending_clients": list(_pending_queue.queue),
        }


def init_scheduler(app):
    """Inicializa o scheduler e carrega todos os clientes ativos."""
    if scheduler.running:
        logger.info("Scheduler ja esta rodando")
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

    # Executa todos os clientes imediatamente na inicializacao
    # para garantir que nao perderam ciclos durante downtime
    for client in active_clients:
        _pending_queue.put(client.id)

    if active_clients:
        _ensure_queue_processor()
        logger.info(f"Execucao inicial agendada para {len(active_clients)} cliente(s)")
