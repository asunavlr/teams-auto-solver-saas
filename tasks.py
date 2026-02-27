"""
Celery tasks para execucao paralela de clientes.

Cada worker pode executar tarefas de clientes independentemente.
"""

import os
import sys

# Adiciona o diretorio atual ao path para encontrar modulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from datetime import datetime
from pathlib import Path
from celery import Celery
from loguru import logger

import config as cfg

# Configura loguru para escrever em arquivo compartilhado
LOG_FILE = Path("/app/logs/worker.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logger.add(
    LOG_FILE,
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",
)

# Configura Celery
celery = Celery(
    "tasks",
    broker=cfg.REDIS_URL,
    backend=cfg.REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=cfg.TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1200,  # 20 minutos max por tarefa
    task_soft_time_limit=1140,  # Warning aos 19 minutos
    worker_prefetch_multiplier=1,  # Pega 1 tarefa por vez
    task_acks_late=True,  # Confirma apenas apos completar
)


def get_app_context():
    """Cria contexto da aplicacao Flask."""
    from web import create_app
    app = create_app()
    return app.app_context()


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def executar_cliente(self, client_id: int):
    """
    Executa ciclo de monitoramento para um cliente.

    Args:
        client_id: ID do cliente

    Returns:
        Dict com resultado da execucao
    """
    logger.info(f"[Celery] Iniciando execucao do cliente {client_id}")

    with get_app_context():
        from web import db
        from web.models import Client, TaskLog, ClientStatus

        # Busca cliente
        client = Client.query.get(client_id)
        if not client:
            logger.error(f"Cliente {client_id} nao encontrado")
            return {"error": "Cliente nao encontrado"}

        # Verifica se esta ativo
        if not client.is_active:
            logger.info(f"Cliente {client.nome} nao esta ativo")
            ClientStatus.set_status(client_id, "idle", "Cliente inativo")
            return {"error": "Cliente inativo"}

        # Verifica limite do plano
        if client.limite_atingido:
            logger.info(f"Cliente {client.nome} atingiu limite do plano")
            ClientStatus.set_status(
                client_id, "idle",
                f"Limite atingido: {client.tarefas_mes}/{client.limite_tarefas}"
            )
            return {"error": "Limite de tarefas atingido"}

        # Atualiza status para running
        ClientStatus.set_status(client_id, "running", "Iniciando monitoramento")

        try:
            # Importa e executa o ciclo de monitoramento
            from engine.monitor import ciclo_monitoramento_cliente, ClientConfig

            # Garante contador atualizado
            client.verificar_reset_mensal()

            config = ClientConfig(
                client_id=client.id,
                nome=client.nome,
                teams_email=client.teams_email,
                teams_password=client.teams_password,
                anthropic_key=client.anthropic_key,
                smtp_email=client.smtp_email,
                smtp_password=client.smtp_password,
                notification_email=client.notification_email,
                whatsapp=client.whatsapp,
                check_interval=client.check_interval,
                data_dir=client.data_dir,
                limite_tarefas=client.limite_tarefas,
                tarefas_mes=client.tarefas_mes,
            )

            # Executa o ciclo (async)
            resultado = asyncio.run(ciclo_monitoramento_cliente(config))

            # Processa resultados
            tasks_success = 0
            tasks_error = 0

            # Limpa qualquer transacao pendente antes de salvar
            try:
                db.session.rollback()
            except Exception:
                pass

            for task in resultado.get("tasks", []):
                try:
                    # Salva log
                    task_log = TaskLog(
                        client_id=client_id,
                        task_name=task.get("name", ""),
                        discipline=task.get("discipline", ""),
                        format=task.get("format", ""),
                        status=task.get("status", "error"),
                        error_msg=task.get("error", ""),
                    )
                    db.session.add(task_log)

                    # Conta e incrementa
                    if task.get("status") == "success":
                        client.incrementar_tarefa()
                        tasks_success += 1
                    elif task.get("status") == "error":
                        tasks_error += 1
                except Exception as e:
                    logger.error(f"Erro ao salvar log da tarefa: {e}")
                    try:
                        db.session.rollback()
                    except Exception:
                        pass

            # Atualiza ultimo check
            try:
                client.last_check = datetime.utcnow()
                db.session.commit()
            except Exception as e:
                logger.error(f"Erro ao fazer commit: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass

            # Status final
            if tasks_error > 0:
                ClientStatus.set_status(
                    client_id, "idle",
                    f"Concluido: {tasks_success} OK, {tasks_error} erros"
                )
            elif tasks_success > 0:
                ClientStatus.set_status(
                    client_id, "idle",
                    f"Concluido: {tasks_success} tarefa(s) enviada(s)"
                )
            else:
                ClientStatus.set_status(
                    client_id, "idle",
                    "Nenhuma tarefa nova encontrada"
                )

            logger.info(
                f"[Celery] Cliente {client.nome} concluido: "
                f"{tasks_success} sucesso, {tasks_error} erros"
            )

            return {
                "client_id": client_id,
                "success": tasks_success,
                "errors": tasks_error,
                "tasks": resultado.get("tasks", [])
            }

        except Exception as e:
            logger.exception(f"[Celery] Erro ao executar cliente {client_id}: {e}")

            # Atualiza status com erro
            ClientStatus.set_status(client_id, "error", str(e)[:200])

            # Notifica admin
            try:
                from engine.whatsapp import notificar_admin_erro
                notificar_admin_erro(client.nome, str(e))
            except:
                pass

            # Retry se nao excedeu tentativas
            if self.request.retries < self.max_retries:
                logger.info(f"[Celery] Retry {self.request.retries + 1}/{self.max_retries} para cliente {client_id}")
                raise self.retry(exc=e)

            return {"error": str(e)}


@celery.task
def health_check():
    """Task de health check para verificar se o worker esta funcionando."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
