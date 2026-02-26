"""API de logs com paginacao e export CSV."""

import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, request, Response

from web import db
from web.models import Client, TaskLog
from web.api_auth import jwt_or_session_required

api_logs_bp = Blueprint("api_logs", __name__, url_prefix="/api/logs")


@api_logs_bp.route("")
@jwt_or_session_required
def list_logs():
    """Lista logs paginados com filtros."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    client_id = request.args.get("client_id", type=int)
    status = request.args.get("status")
    search = request.args.get("search", "").strip()
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    query = TaskLog.query.join(Client)

    if client_id:
        query = query.filter(TaskLog.client_id == client_id)
    if status:
        query = query.filter(TaskLog.status == status)
    if search:
        query = query.filter(
            db.or_(
                TaskLog.task_name.ilike(f"%{search}%"),
                TaskLog.discipline.ilike(f"%{search}%"),
            )
        )
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            query = query.filter(TaskLog.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            query = query.filter(TaskLog.created_at <= dt)
        except ValueError:
            pass

    query = query.order_by(TaskLog.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [{
            "id": log.id,
            "client_id": log.client_id,
            "client_name": log.client.nome,
            "task_name": log.task_name,
            "discipline": log.discipline,
            "format": log.format,
            "status": log.status,
            "error_msg": log.error_msg,
            "created_at": log.created_at.isoformat(),
        } for log in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "per_page": paginated.per_page,
        "pages": paginated.pages,
    })


@api_logs_bp.route("/export")
@jwt_or_session_required
def export_csv():
    """Exporta logs como CSV."""
    client_id = request.args.get("client_id", type=int)
    status = request.args.get("status")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    query = TaskLog.query.join(Client)

    if client_id:
        query = query.filter(TaskLog.client_id == client_id)
    if status:
        query = query.filter(TaskLog.status == status)
    if date_from:
        try:
            query = query.filter(TaskLog.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(TaskLog.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    query = query.order_by(TaskLog.created_at.desc())
    logs = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data", "Cliente", "Tarefa", "Disciplina", "Formato", "Status", "Erro"])

    for log in logs:
        writer.writerow([
            log.created_at.strftime("%d/%m/%Y %H:%M"),
            log.client.nome,
            log.task_name,
            log.discipline,
            log.format,
            log.status,
            log.error_msg or "",
        ])

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs_export.csv"},
    )
