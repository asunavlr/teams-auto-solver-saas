"""
Scheduler multi-cliente com APScheduler.
Gerencia jobs de monitoramento por cliente.

Suporta dois modos:
- Celery (padrao com Docker): tarefas enviadas para workers paralelos
- Local (fallback): execucao serial no mesmo processo
"""

import asyncio
import os
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

# Modo de execucao: "celery" ou "local"
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "celery" if os.getenv("REDIS_URL") else "local")


def _get_app_context():
    """Obtem contexto do Flask para acessar o banco."""
    from web import create_app
    app = create_app()
    return app.app_context()


def _build_client_config(client):
    """Constroi ClientConfig a partir do modelo do banco."""
    from engine.monitor import ClientConfig
    # Garante contador atualizado
    client.verificar_reset_mensal()
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
        whatsapp=getattr(client, 'whatsapp', ''),
        limite_tarefas=client.limite_tarefas,
        tarefas_mes=client.tarefas_mes,
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


def _update_client_status(app, client_id: int, status: str, action: str = "", error: str = ""):
    """Atualiza status do cliente no banco (dentro do contexto do app)."""
    try:
        from web.models import ClientStatus
        from web import db

        with app.app_context():
            ClientStatus.set_status(client_id, status, action, error)
    except Exception as e:
        logger.debug(f"Erro ao atualizar status: {e}")


def _execute_client(client_id: int):
    """Executa o ciclo de monitoramento para um cliente."""
    global _running_client

    # Marca como em execucao
    with _lock:
        _running_client = client_id

    app = None
    try:
        from web import db, create_app
        from web.models import Client, TaskLog

        app = create_app()

        # Atualiza status para "running"
        _update_client_status(app, client_id, "running", "Iniciando ciclo...")

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
                _update_client_status(app, client_id, "idle", "Cliente inativo")
                return

            # Verifica limite de tarefas do plano
            if client.limite_atingido:
                logger.info(f"Cliente {client.nome} atingiu limite de tarefas ({client.tarefas_mes}/{client.limite_tarefas})")
                _update_client_status(app, client_id, "idle", f"Limite atingido: {client.tarefas_mes}/{client.limite_tarefas} tarefas")
                return

            config = _build_client_config(client)
            client_nome = client.nome

        # Executa o ciclo async (fora do app_context pra nao bloquear)
        from engine.monitor import ciclo_monitoramento_cliente

        loop = asyncio.new_event_loop()
        try:
            resultado = loop.run_until_complete(ciclo_monitoramento_cliente(config))
        finally:
            loop.close()

        # Atualiza banco com resultados
        with app.app_context():
            client = db.session.get(Client, client_id)
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
                    client.incrementar_tarefa()  # Incrementa contador do plano

            db.session.commit()

        # Atualiza status final
        success_count = resultado.get("success", 0)
        error_count = resultado.get("error", 0)
        if error_count > 0:
            _update_client_status(app, client_id, "idle", f"Concluido: {error_count} erro(s)")
        else:
            _update_client_status(app, client_id, "idle", f"Concluido: {success_count} tarefa(s)")

        logger.info(f"Cliente {client_nome}: ciclo concluido")

        # Envia notificacao WhatsApp se configurado
        if config.whatsapp and (success_count > 0 or error_count > 0):
            try:
                from engine.whatsapp import notificar_ciclo_concluido
                notificar_ciclo_concluido(config.whatsapp, config.nome, success_count, error_count)
            except Exception as e:
                logger.debug(f"Erro ao enviar WhatsApp: {e}")

    except Exception as e:
        logger.error(f"Erro no job do cliente {client_id}: {e}")
        if app:
            _update_client_status(app, client_id, "error", "", str(e))

            # Notifica admin sobre erro
            try:
                import config as cfg
                if cfg.ADMIN_WHATSAPP:
                    from engine.whatsapp import notificar_admin_erro
                    notificar_admin_erro(cfg.ADMIN_WHATSAPP, client_nome if 'client_nome' in dir() else f"ID {client_id}", str(e), client_id)
            except Exception:
                pass
    finally:
        with _lock:
            _running_client = None


def _run_client_sync(client_id: int):
    """Agenda execucao de um cliente (Celery ou fila local)."""
    global _running_client

    # Modo Celery: envia para worker
    if EXECUTION_MODE == "celery":
        try:
            from tasks import executar_cliente
            executar_cliente.delay(client_id)
            logger.info(f"[Celery] Tarefa enviada para cliente {client_id}")
            return
        except Exception as e:
            logger.warning(f"Celery indisponivel, usando modo local: {e}")

    # Modo local: fila serial
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


def run_client_now(client_id: int, use_celery: bool = True):
    """Executa o monitoramento de um cliente imediatamente.

    Args:
        client_id: ID do cliente
        use_celery: Se True, envia para Celery worker (paralelo).
                    Se False, executa na fila local do app.
    """
    if use_celery:
        try:
            from tasks import executar_cliente
            executar_cliente.delay(client_id)
            logger.info(f"Execucao imediata enviada ao Celery: cliente {client_id}")
            return
        except Exception as e:
            logger.warning(f"Celery indisponivel, usando fila local: {e}")

    # Fallback para fila local
    _pending_queue.put(client_id)
    _ensure_queue_processor()
    logger.info(f"Execucao imediata agendada (local): cliente {client_id}")


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

    clients_to_run_now = []

    with app.app_context():
        from web.models import Client
        from web import db

        active_clients = Client.query.filter_by(status="active").all()
        active_clients = [c for c in active_clients if c.is_active]

        now = datetime.utcnow()

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

            # Verifica se precisa rodar imediatamente
            # (nunca rodou OU perdeu ciclo durante downtime)
            needs_immediate_run = False
            if client.last_check is None:
                needs_immediate_run = True
                reason = "nunca executado"
            else:
                # Calcula quando deveria ter rodado
                from datetime import timedelta
                next_expected = client.last_check + timedelta(minutes=client.check_interval)
                if next_expected < now:
                    needs_immediate_run = True
                    minutes_late = int((now - next_expected).total_seconds() / 60)
                    reason = f"atrasado {minutes_late} min"
                else:
                    minutes_until = int((next_expected - now).total_seconds() / 60)
                    reason = f"proximo em {minutes_until} min"

            if needs_immediate_run:
                clients_to_run_now.append(client.id)
                logger.info(f"Job carregado: {client.nome} ({reason}) - EXECUTAR AGORA")
            else:
                logger.info(f"Job carregado: {client.nome} ({reason})")

    scheduler.start()
    logger.info(f"Scheduler iniciado com {len(active_clients)} cliente(s) ativo(s)")

    # Executa apenas clientes que perderam ciclos
    if clients_to_run_now:
        if EXECUTION_MODE == "celery":
            try:
                from tasks import executar_cliente
                for client_id in clients_to_run_now:
                    executar_cliente.delay(client_id)
                logger.info(f"[Celery] Execucao imediata enviada para {len(clients_to_run_now)} cliente(s)")
            except Exception as e:
                logger.warning(f"Celery indisponivel no init, usando fila local: {e}")
                for client_id in clients_to_run_now:
                    _pending_queue.put(client_id)
                _ensure_queue_processor()
        else:
            for client_id in clients_to_run_now:
                _pending_queue.put(client_id)
            _ensure_queue_processor()
            logger.info(f"Execucao imediata (local) para {len(clients_to_run_now)} cliente(s)")
    else:
        logger.info("Nenhum cliente perdeu ciclos, aguardando intervalos normais")
