"""API de logs com paginacao e export CSV."""

import csv
import io
import json
import mimetypes
import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, Response, send_file, abort
from werkzeug.utils import secure_filename

from web import db
from web.models import Client, TaskLog
from web.api_auth import jwt_or_session_required
import config as cfg

WORKER_LOG_FILE = Path("/app/logs/worker.log")
UPLOAD_FOLDER = Path(cfg.BASE_DIR) / "uploads" / "resubmit"

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


@api_logs_bp.route("/worker")
@jwt_or_session_required
def worker_logs():
    """Retorna ultimas linhas do log do worker Celery."""
    lines = request.args.get("lines", 100, type=int)
    lines = min(lines, 500)  # Max 500 linhas

    if not WORKER_LOG_FILE.exists():
        return jsonify({"lines": [], "total": 0})

    try:
        with open(WORKER_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()

        # Pega ultimas N linhas
        last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return jsonify({
            "lines": [line.rstrip() for line in last_lines],
            "total": len(all_lines),
        })
    except Exception as e:
        return jsonify({"error": str(e), "lines": [], "total": 0})


@api_logs_bp.route("/<int:log_id>")
@jwt_or_session_required
def get_log_detail(log_id):
    """Retorna detalhes completos de um log de tarefa."""
    log = TaskLog.query.get_or_404(log_id)

    # Parse arquivos_enviados se existir
    arquivos = []
    if log.arquivos_enviados:
        try:
            arquivos = json.loads(log.arquivos_enviados)
        except (json.JSONDecodeError, TypeError):
            arquivos = []

    # Parse debug_data se existir
    debug = None
    if log.debug_data:
        try:
            debug = json.loads(log.debug_data)
        except (json.JSONDecodeError, TypeError):
            debug = None

    return jsonify({
        "id": log.id,
        "client_id": log.client_id,
        "client_name": log.client.nome,
        "task_name": log.task_name,
        "discipline": log.discipline,
        "format": log.format,
        "status": log.status,
        "error_msg": log.error_msg,
        "created_at": log.created_at.isoformat(),
        "instrucoes": log.instrucoes or "",
        "resposta": log.resposta or "",
        "arquivos_enviados": arquivos,
        "debug": debug,
    })


@api_logs_bp.route("/<int:log_id>/files/<int:file_index>")
@jwt_or_session_required
def download_file(log_id, file_index):
    """Download de arquivo anexo de uma tarefa."""
    log = TaskLog.query.get_or_404(log_id)

    # Parse arquivos_enviados
    arquivos = []
    if log.arquivos_enviados:
        try:
            arquivos = json.loads(log.arquivos_enviados)
        except (json.JSONDecodeError, TypeError):
            arquivos = []

    if not arquivos or file_index < 0 or file_index >= len(arquivos):
        abort(404, description="Arquivo não encontrado")

    file_path = arquivos[file_index]

    # Verifica se o caminho é relativo ou absoluto
    if not os.path.isabs(file_path):
        # Se relativo, assume que está em relação ao diretório base
        file_path = os.path.join(cfg.BASE_DIR, file_path)

    # Verifica se arquivo existe
    if not os.path.exists(file_path):
        abort(404, description="Arquivo não encontrado no servidor")

    # Determina o mimetype
    mimetype, _ = mimetypes.guess_type(file_path)
    if not mimetype:
        mimetype = "application/octet-stream"

    # Extrai nome do arquivo
    filename = os.path.basename(file_path)

    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename
    )


@api_logs_bp.route("/<int:log_id>/undo", methods=["POST"])
@jwt_or_session_required
def undo_submission(log_id):
    """Desfaz o envio de uma tarefa."""
    log = TaskLog.query.get_or_404(log_id)

    # Verifica se pode desfazer
    if log.status != "success":
        return jsonify({"error": "Apenas tarefas enviadas podem ser desfeitas"}), 400

    # Pega parametro reprocessar
    data = request.get_json() or {}
    reprocessar = data.get("reprocessar", False)

    # Cria task Celery
    from tasks import desfazer_envio_tarefa
    task = desfazer_envio_tarefa.delay(log_id, reprocessar)

    return jsonify({
        "message": "Processando desfazer envio...",
        "task_id": task.id,
        "log_id": log_id,
        "reprocessar": reprocessar,
    })


@api_logs_bp.route("/<int:log_id>/resubmit", methods=["POST"])
@jwt_or_session_required
def resubmit_with_files(log_id):
    """Desfaz envio e reenvia com novos arquivos."""
    log = TaskLog.query.get_or_404(log_id)

    # Verifica se pode reenviar
    if log.status not in ("success", "success_flagged"):
        return jsonify({"error": "Apenas tarefas enviadas podem ser reenviadas"}), 400

    # Verifica se tem arquivos
    if "files" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "Nenhum arquivo selecionado"}), 400

    # Cria pasta temporaria para os arquivos
    upload_id = str(uuid.uuid4())
    upload_path = UPLOAD_FOLDER / upload_id
    upload_path.mkdir(parents=True, exist_ok=True)

    saved_files = []
    try:
        for file in files:
            if file.filename:
                filename = secure_filename(file.filename)
                filepath = upload_path / filename
                file.save(str(filepath))
                saved_files.append(str(filepath))
    except Exception as e:
        return jsonify({"error": f"Erro ao salvar arquivos: {str(e)}"}), 500

    if not saved_files:
        return jsonify({"error": "Nenhum arquivo foi salvo"}), 400

    # Cria task Celery para reenvio
    from tasks import reenviar_tarefa_com_arquivos
    task = reenviar_tarefa_com_arquivos.delay(log_id, saved_files)

    return jsonify({
        "message": "Processando reenvio com novos arquivos...",
        "task_id": task.id,
        "log_id": log_id,
        "files_count": len(saved_files),
    })
