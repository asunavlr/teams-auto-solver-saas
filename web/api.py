"""API endpoints para dados em tempo real."""

import os
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_login import login_required

import config as cfg
from web import db
from web.models import Client, TaskLog, ClientStatus
from web.api_auth import jwt_or_session_required

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Cache para posicao do arquivo de log
_log_positions = {}


# ============================================
# HEALTH CHECK (sem autenticacao)
# ============================================

@api_bp.route("/health")
def health_check():
    """
    Health check endpoint para monitoramento.
    Verifica: banco de dados, scheduler, redis (se disponivel).
    """
    import psutil

    checks = {}
    healthy = True

    # Check: Database
    try:
        db.session.execute(db.text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)[:100]}
        healthy = False

    # Check: Scheduler
    try:
        from engine.scheduler import scheduler
        if scheduler.running:
            checks["scheduler"] = {"status": "ok", "jobs": len(scheduler.get_jobs())}
        else:
            checks["scheduler"] = {"status": "error", "message": "Scheduler not running"}
            healthy = False
    except Exception as e:
        checks["scheduler"] = {"status": "error", "message": str(e)[:100]}
        healthy = False

    # Check: Redis (opcional)
    try:
        import redis
        r = redis.from_url(cfg.REDIS_URL)
        r.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as e:
        # Redis e opcional (modo local funciona sem)
        checks["redis"] = {"status": "unavailable", "message": str(e)[:50]}

    # Check: Disk space
    try:
        disk = psutil.disk_usage("/")
        free_gb = disk.free / (1024 * 1024 * 1024)
        if free_gb < 1:
            checks["disk"] = {"status": "warning", "free_gb": round(free_gb, 2)}
        else:
            checks["disk"] = {"status": "ok", "free_gb": round(free_gb, 2)}
    except Exception:
        checks["disk"] = {"status": "unknown"}

    # Check: Memory
    try:
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            checks["memory"] = {"status": "warning", "percent": memory.percent}
            healthy = False
        else:
            checks["memory"] = {"status": "ok", "percent": memory.percent}
    except Exception:
        checks["memory"] = {"status": "unknown"}

    return jsonify({
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks
    }), 200 if healthy else 503


def get_local_now():
    """Retorna datetime atual no fuso horario configurado."""
    try:
        tz = ZoneInfo(cfg.TIMEZONE)
        return datetime.now(tz)
    except Exception:
        # Fallback para UTC-3 (Brasilia)
        return datetime.now(timezone(timedelta(hours=-3)))


def get_today_start():
    """Retorna inicio do dia no fuso horario local."""
    now = get_local_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@api_bp.route("/dashboard/stats")
@jwt_or_session_required
def dashboard_stats():
    """Retorna estatisticas expandidas do dashboard."""
    today_start = get_today_start()
    today_start_naive = today_start.replace(tzinfo=None)
    week_start = today_start_naive - timedelta(days=7)
    month_start = today_start_naive - timedelta(days=30)

    all_clients = Client.query.all()

    # Contagens basicas
    tasks_today = TaskLog.query.filter(TaskLog.created_at >= today_start_naive).count()
    tasks_week = TaskLog.query.filter(TaskLog.created_at >= week_start).count()
    tasks_month = TaskLog.query.filter(TaskLog.created_at >= month_start).count()

    # Taxa de sucesso
    success_count = TaskLog.query.filter(TaskLog.status == "success").count()
    total_tasks = TaskLog.query.count()
    success_rate = round((success_count / total_tasks * 100) if total_tasks > 0 else 0, 1)

    # Erros recentes (ultimas 24h)
    errors_24h = TaskLog.query.filter(
        TaskLog.created_at >= today_start_naive - timedelta(hours=24),
        TaskLog.status == "error"
    ).count()

    # Media por dia (ultimos 30 dias)
    avg_per_day = round(tasks_month / 30, 1) if tasks_month > 0 else 0

    stats = {
        "total_clients": len(all_clients),
        "active_clients": sum(1 for c in all_clients if c.is_active),
        "expired_clients": sum(1 for c in all_clients if c.is_expired),
        "paused_clients": sum(1 for c in all_clients if c.status == "paused"),
        "tasks_today": tasks_today,
        "tasks_week": tasks_week,
        "tasks_month": tasks_month,
        "total_tasks": total_tasks,
        "success_rate": success_rate,
        "errors_24h": errors_24h,
        "avg_per_day": avg_per_day,
    }

    return jsonify(stats)


@api_bp.route("/clients/status")
@jwt_or_session_required
def clients_status():
    """Retorna status de todos os clientes."""
    from engine.scheduler import scheduler

    clients = Client.query.all()
    result = []

    for client in clients:
        status_info = ClientStatus.query.filter_by(client_id=client.id).first()

        last_task = TaskLog.query.filter_by(client_id=client.id)\
            .order_by(TaskLog.created_at.desc()).first()

        # Calcula taxa de sucesso do cliente
        client_total = TaskLog.query.filter_by(client_id=client.id).count()
        client_success = TaskLog.query.filter_by(client_id=client.id, status="success").count()
        client_success_rate = round((client_success / client_total * 100) if client_total > 0 else 0, 1)

        # Proximo check agendado
        next_check = None
        try:
            job = scheduler.get_job(f"client_{client.id}")
            if job and job.next_run_time:
                next_check = job.next_run_time.isoformat()
        except Exception:
            pass

        result.append({
            "id": client.id,
            "nome": client.nome,
            "subscription_status": "active" if client.is_active else ("paused" if client.status == "paused" else "expired"),
            "days_remaining": client.days_remaining,
            "current_status": status_info.status if status_info else "idle",
            "current_action": status_info.current_action if status_info else None,
            "last_check": client.last_check.isoformat() if client.last_check else None,
            "next_check": next_check,
            "last_task": {
                "name": last_task.task_name,
                "status": last_task.status,
                "time": last_task.created_at.isoformat()
            } if last_task else None,
            "tasks_completed": client.tasks_completed,
            "success_rate": client_success_rate,
            "check_interval": client.check_interval,
            # Plan info
            "plan_name": client.plan.nome if client.plan else None,
            "tarefas_mes": client.tarefas_mes,
            "limite_tarefas": client.limite_tarefas,
            "uso_percentual": client.uso_percentual,
            "limite_atingido": client.limite_atingido,
        })

    return jsonify(result)


@api_bp.route("/clients/<int:client_id>/status")
@jwt_or_session_required
def client_status(client_id):
    """Retorna status detalhado de um cliente."""
    client = Client.query.get_or_404(client_id)
    status_info = ClientStatus.query.filter_by(client_id=client_id).first()

    recent_logs = TaskLog.query.filter_by(client_id=client_id)\
        .order_by(TaskLog.created_at.desc()).limit(10).all()

    return jsonify({
        "id": client.id,
        "nome": client.nome,
        "subscription_status": "active" if client.is_active else ("paused" if client.status == "paused" else "expired"),
        "current_status": status_info.status if status_info else "idle",
        "current_action": status_info.current_action if status_info else None,
        "started_at": status_info.started_at.isoformat() if status_info and status_info.started_at else None,
        "last_check": client.last_check.isoformat() if client.last_check else None,
        "last_error": status_info.last_error if status_info else None,
        "tasks_completed": client.tasks_completed,
        "recent_logs": [{
            "task_name": log.task_name,
            "discipline": log.discipline,
            "format": log.format,
            "status": log.status,
            "error_msg": log.error_msg,
            "created_at": log.created_at.isoformat()
        } for log in recent_logs]
    })


@api_bp.route("/logs/recent")
@jwt_or_session_required
def recent_logs():
    """Retorna logs recentes (para atualizacao em tempo real)."""
    limit = request.args.get("limit", 20, type=int)
    client_id = request.args.get("client_id", type=int)
    after = request.args.get("after")  # timestamp ISO para pegar apenas novos

    query = TaskLog.query.order_by(TaskLog.created_at.desc())

    if client_id:
        query = query.filter_by(client_id=client_id)

    if after:
        try:
            after_dt = datetime.fromisoformat(after.replace("Z", "+00:00"))
            query = query.filter(TaskLog.created_at > after_dt)
        except ValueError:
            pass

    logs = query.limit(limit).all()

    return jsonify([{
        "id": log.id,
        "client_id": log.client_id,
        "client_name": log.client.nome,
        "task_name": log.task_name,
        "discipline": log.discipline,
        "format": log.format,
        "status": log.status,
        "error_msg": log.error_msg,
        "created_at": log.created_at.isoformat()
    } for log in logs])


@api_bp.route("/activity/timeline")
@jwt_or_session_required
def activity_timeline():
    """Retorna timeline de atividade por hora (ultimas 24h)."""
    now = get_local_now().replace(tzinfo=None)
    start = now - timedelta(hours=24)

    logs = TaskLog.query.filter(TaskLog.created_at >= start).all()

    # Agrupa por hora
    hours = {}
    for i in range(24):
        hour = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
        hours[hour.isoformat()] = {"success": 0, "error": 0}

    for log in logs:
        hour = log.created_at.replace(minute=0, second=0, microsecond=0)
        key = hour.isoformat()
        if key in hours:
            if log.status == "success":
                hours[key]["success"] += 1
            else:
                hours[key]["error"] += 1

    return jsonify([
        {"hour": k, **v}
        for k, v in sorted(hours.items())
    ])


@api_bp.route("/activity/daily")
@jwt_or_session_required
def activity_daily():
    """Retorna atividade por dia (ultimos 7 dias)."""
    today = get_today_start().replace(tzinfo=None)

    days = []
    for i in range(7):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        success = TaskLog.query.filter(
            TaskLog.created_at >= day_start,
            TaskLog.created_at < day_end,
            TaskLog.status == "success"
        ).count()

        errors = TaskLog.query.filter(
            TaskLog.created_at >= day_start,
            TaskLog.created_at < day_end,
            TaskLog.status == "error"
        ).count()

        other = TaskLog.query.filter(
            TaskLog.created_at >= day_start,
            TaskLog.created_at < day_end,
            TaskLog.status.notin_(["success", "error"])
        ).count()

        days.append({
            "date": day_start.strftime("%d/%m"),
            "weekday": ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"][day_start.weekday()],
            "success": success,
            "errors": errors,
            "other": other,
            "total": success + errors + other
        })

    return jsonify(list(reversed(days)))


@api_bp.route("/system/status")
@jwt_or_session_required
def system_status():
    """Retorna status do sistema."""
    import psutil
    import os

    # Uptime do processo
    try:
        import time
        process = psutil.Process(os.getpid())
        uptime_seconds = time.time() - process.create_time()
        uptime_hours = int(uptime_seconds // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{uptime_hours}h {uptime_minutes}m"
    except Exception:
        uptime = "N/A"

    # Memoria
    try:
        memory = psutil.virtual_memory()
        memory_used = round(memory.used / (1024 * 1024 * 1024), 1)
        memory_total = round(memory.total / (1024 * 1024 * 1024), 1)
        memory_percent = memory.percent
    except Exception:
        memory_used = memory_total = memory_percent = 0

    # CPU
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
    except Exception:
        cpu_percent = 0

    # Scheduler status
    try:
        from engine.scheduler import scheduler
        scheduler_running = scheduler.running
        scheduler_jobs = len(scheduler.get_jobs())
    except Exception:
        scheduler_running = False
        scheduler_jobs = 0

    return jsonify({
        "uptime": uptime,
        "memory_used_gb": memory_used,
        "memory_total_gb": memory_total,
        "memory_percent": memory_percent,
        "cpu_percent": cpu_percent,
        "scheduler_running": scheduler_running,
        "scheduler_jobs": scheduler_jobs
    })


@api_bp.route("/errors/recent")
@jwt_or_session_required
def recent_errors():
    """Retorna erros recentes."""
    limit = request.args.get("limit", 10, type=int)

    errors = TaskLog.query.filter(
        TaskLog.status == "error"
    ).order_by(TaskLog.created_at.desc()).limit(limit).all()

    return jsonify([{
        "id": e.id,
        "client_name": e.client.nome,
        "task_name": e.task_name,
        "error_msg": e.error_msg,
        "created_at": e.created_at.isoformat()
    } for e in errors])


@api_bp.route("/scheduler/jobs")
@jwt_or_session_required
def scheduler_jobs():
    """Retorna jobs agendados no scheduler."""
    try:
        from engine.scheduler import scheduler, get_queue_status

        jobs = []
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "next_run_formatted": next_run.strftime("%d/%m %H:%M") if next_run else "N/A"
            })

        # Adiciona status da fila
        queue_status = get_queue_status()

        return jsonify({
            "running": scheduler.running,
            "jobs": jobs,
            "queue": queue_status
        })
    except Exception as e:
        return jsonify({"running": False, "jobs": [], "queue": {}, "error": str(e)})


@api_bp.route("/server/logs")
@jwt_or_session_required
def server_logs():
    """Retorna logs do servidor (arquivo app.log)."""
    lines = request.args.get("lines", 100, type=int)
    after_line = request.args.get("after", 0, type=int)

    # Caminho do arquivo de log
    log_file = Path(__file__).parent.parent / "logs" / "app.log"

    if not log_file.exists():
        return jsonify({"lines": [], "last_line": 0, "total_lines": 0})

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # Se after_line especificado, retorna apenas linhas novas
        if after_line > 0 and after_line < total_lines:
            new_lines = all_lines[after_line:]
            return jsonify({
                "lines": [line.rstrip() for line in new_lines[-lines:]],
                "last_line": total_lines,
                "total_lines": total_lines,
                "new_count": len(new_lines)
            })

        # Retorna ultimas N linhas
        recent_lines = all_lines[-lines:] if lines < total_lines else all_lines

        return jsonify({
            "lines": [line.rstrip() for line in recent_lines],
            "last_line": total_lines,
            "total_lines": total_lines
        })

    except Exception as e:
        return jsonify({"error": str(e), "lines": [], "last_line": 0})


@api_bp.route("/server/logs/stream")
@jwt_or_session_required
def server_logs_stream():
    """Retorna novas linhas do log desde a ultima posicao."""
    session_id = request.args.get("session", "default")
    lines_limit = request.args.get("lines", 50, type=int)

    log_file = Path(__file__).parent.parent / "logs" / "app.log"

    if not log_file.exists():
        return jsonify({"lines": [], "position": 0})

    try:
        # Obtem posicao anterior
        last_pos = _log_positions.get(session_id, 0)

        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            # Vai para o final para saber o tamanho
            f.seek(0, 2)
            file_size = f.tell()

            # Se arquivo foi truncado/rotacionado, reinicia
            if last_pos > file_size:
                last_pos = 0

            # Se primeira vez, pega ultimas N linhas
            if last_pos == 0:
                f.seek(0)
                all_lines = f.readlines()
                lines = all_lines[-lines_limit:]
                _log_positions[session_id] = file_size
                return jsonify({
                    "lines": [l.rstrip() for l in lines],
                    "position": file_size,
                    "is_initial": True
                })

            # Le novas linhas
            f.seek(last_pos)
            new_content = f.read()
            new_pos = f.tell()

            _log_positions[session_id] = new_pos

            if new_content:
                lines = new_content.splitlines()
                return jsonify({
                    "lines": lines[-lines_limit:],
                    "position": new_pos,
                    "new_count": len(lines)
                })

            return jsonify({
                "lines": [],
                "position": new_pos
            })

    except Exception as e:
        return jsonify({"error": str(e), "lines": [], "position": 0})
