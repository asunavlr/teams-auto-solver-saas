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

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Cache para posicao do arquivo de log
_log_positions = {}


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
@login_required
def dashboard_stats():
    """Retorna estatisticas do dashboard."""
    today_start = get_today_start()
    # Remove timezone para comparar com datetime naive do banco
    today_start_naive = today_start.replace(tzinfo=None)

    all_clients = Client.query.all()

    stats = {
        "total_clients": len(all_clients),
        "active_clients": sum(1 for c in all_clients if c.is_active),
        "expired_clients": sum(1 for c in all_clients if c.is_expired),
        "tasks_today": TaskLog.query.filter(
            TaskLog.created_at >= today_start_naive
        ).count(),
        "tasks_week": TaskLog.query.filter(
            TaskLog.created_at >= today_start_naive - timedelta(days=7)
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


@api_bp.route("/server/logs")
@login_required
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
@login_required
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
