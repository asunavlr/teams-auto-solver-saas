"""API endpoints para dados em tempo real."""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_login import login_required
from web import db
from web.models import Client, TaskLog, ClientStatus

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/dashboard/stats")
@login_required
def dashboard_stats():
    """Retorna estatisticas do dashboard."""
    now = datetime.utcnow()
    all_clients = Client.query.all()

    stats = {
        "total_clients": len(all_clients),
        "active_clients": sum(1 for c in all_clients if c.is_active),
        "expired_clients": sum(1 for c in all_clients if c.is_expired),
        "tasks_today": TaskLog.query.filter(
            TaskLog.created_at >= now.replace(hour=0, minute=0, second=0)
        ).count(),
        "tasks_week": TaskLog.query.filter(
            TaskLog.created_at >= now - timedelta(days=7)
        ).count(),
    }

    return jsonify(stats)


@api_bp.route("/clients/status")
@login_required
def clients_status():
    """Retorna status de todos os clientes."""
    clients = Client.query.all()
    result = []

    for client in clients:
        status_info = ClientStatus.query.filter_by(client_id=client.id).first()

        last_task = TaskLog.query.filter_by(client_id=client.id)\
            .order_by(TaskLog.created_at.desc()).first()

        result.append({
            "id": client.id,
            "nome": client.nome,
            "subscription_status": "active" if client.is_active else ("paused" if client.status == "paused" else "expired"),
            "days_remaining": client.days_remaining,
            "current_status": status_info.status if status_info else "idle",
            "current_action": status_info.current_action if status_info else None,
            "last_check": client.last_check.isoformat() if client.last_check else None,
            "last_task": {
                "name": last_task.task_name,
                "status": last_task.status,
                "time": last_task.created_at.isoformat()
            } if last_task else None,
            "tasks_completed": client.tasks_completed,
        })

    return jsonify(result)


@api_bp.route("/clients/<int:client_id>/status")
@login_required
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
@login_required
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
@login_required
def activity_timeline():
    """Retorna timeline de atividade por hora (ultimas 24h)."""
    now = datetime.utcnow()
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
