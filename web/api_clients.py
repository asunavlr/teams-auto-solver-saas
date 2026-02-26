"""API CRUD de clientes."""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from web import db
from web.models import Client, Plan, Payment, TaskLog, ClientStatus, encrypt_value
from web.api_auth import jwt_or_session_required

api_clients_bp = Blueprint("api_clients", __name__, url_prefix="/api/clients")


def client_to_dict(client: Client, include_logs: bool = False) -> dict:
    """Serializa um cliente para JSON."""
    status_info = ClientStatus.query.filter_by(client_id=client.id).first()

    data = {
        "id": client.id,
        "nome": client.nome,
        "email": client.email,
        "teams_email": client.teams_email,
        "smtp_email": client.smtp_email or "",
        "notification_email": client.notification_email or "",
        "whatsapp": client.whatsapp or "",
        "status": client.status,
        "is_active": client.is_active,
        "is_expired": client.is_expired,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
        "days_remaining": client.days_remaining,
        "check_interval": client.check_interval,
        "last_check": client.last_check.isoformat() if client.last_check else None,
        "tasks_completed": client.tasks_completed,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        # Plano
        "plan_id": client.plan_id,
        "plan_name": client.plan.nome if client.plan else None,
        "plan_price": client.plan.preco_mensal if client.plan else None,
        "tarefas_mes": client.tarefas_mes,
        "limite_tarefas": client.limite_tarefas,
        "uso_percentual": client.uso_percentual,
        # Runtime
        "runtime_status": status_info.status if status_info else "idle",
        "current_action": status_info.current_action if status_info else "",
    }

    if include_logs:
        # Ultimas 20 tarefas
        logs = TaskLog.query.filter_by(client_id=client.id)\
            .order_by(TaskLog.created_at.desc()).limit(20).all()
        data["task_logs"] = [{
            "id": log.id,
            "task_name": log.task_name,
            "discipline": log.discipline,
            "format": log.format,
            "status": log.status,
            "error_msg": log.error_msg,
            "created_at": log.created_at.isoformat(),
        } for log in logs]

        # Pagamentos
        payments = Payment.query.filter_by(client_id=client.id)\
            .order_by(Payment.created_at.desc()).all()
        data["payments"] = [{
            "id": p.id,
            "amount": p.amount,
            "months": p.months,
            "created_at": p.created_at.isoformat(),
        } for p in payments]

        # Taxa de sucesso
        total = TaskLog.query.filter_by(client_id=client.id).count()
        success = TaskLog.query.filter_by(client_id=client.id, status="success").count()
        data["success_rate"] = round((success / total * 100) if total > 0 else 0, 1)

    return data


# ============================================
# LIST
# ============================================

@api_clients_bp.route("")
@jwt_or_session_required
def list_clients():
    """Lista clientes com filtros e paginacao."""
    # Filtros
    status_filter = request.args.get("status")  # active, expired, paused
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = Client.query

    if status_filter == "active":
        query = query.filter(Client.status == "active", Client.expires_at > datetime.utcnow())
    elif status_filter == "expired":
        query = query.filter(Client.expires_at <= datetime.utcnow())
    elif status_filter == "paused":
        query = query.filter(Client.status == "paused")

    if search:
        query = query.filter(
            db.or_(
                Client.nome.ilike(f"%{search}%"),
                Client.email.ilike(f"%{search}%"),
                Client.teams_email.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Client.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [client_to_dict(c) for c in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "per_page": paginated.per_page,
        "pages": paginated.pages,
    })


# ============================================
# CREATE
# ============================================

@api_clients_bp.route("", methods=["POST"])
@jwt_or_session_required
def create_client():
    """Cria novo cliente."""
    data = request.get_json(silent=True) or {}

    # Validacao
    required = ["nome", "email", "teams_email", "teams_password", "anthropic_key"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo obrigatorio: {field}"}), 400

    # Plano
    plan_id = data.get("plan_id")
    if plan_id:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({"error": "Plano nao encontrado"}), 400
    else:
        plan_id = None

    # Meses de assinatura
    months = data.get("months", 1)
    if not isinstance(months, int) or months < 1:
        months = 1

    client = Client(
        nome=data["nome"],
        email=data["email"],
        teams_email=data["teams_email"],
        teams_password=data["teams_password"],
        anthropic_key=data["anthropic_key"],
        smtp_email=data.get("smtp_email", ""),
        smtp_password=data.get("smtp_password", ""),
        notification_email=data.get("notification_email", ""),
        whatsapp=data.get("whatsapp", ""),
        plan_id=plan_id,
        check_interval=data.get("check_interval", 60),
        expires_at=datetime.utcnow() + timedelta(days=30 * months),
        status="active",
    )

    db.session.add(client)
    db.session.flush()  # Pega o ID

    # Pagamento inicial
    amount = data.get("payment_amount", 0)
    if amount and float(amount) > 0:
        payment = Payment(
            client_id=client.id,
            amount=float(amount),
            months=months,
        )
        db.session.add(payment)

    db.session.commit()

    # Agendar no scheduler
    try:
        from engine.scheduler import agendar_cliente
        agendar_cliente(client)
    except Exception:
        pass

    return jsonify(client_to_dict(client)), 201


# ============================================
# DETAIL
# ============================================

@api_clients_bp.route("/<int:client_id>")
@jwt_or_session_required
def get_client(client_id):
    """Retorna cliente completo com logs e pagamentos."""
    client = Client.query.get_or_404(client_id)
    return jsonify(client_to_dict(client, include_logs=True))


# ============================================
# UPDATE
# ============================================

@api_clients_bp.route("/<int:client_id>", methods=["PUT"])
@jwt_or_session_required
def update_client(client_id):
    """Atualiza cliente."""
    client = Client.query.get_or_404(client_id)
    data = request.get_json(silent=True) or {}

    # Campos simples
    if "nome" in data:
        client.nome = data["nome"]
    if "email" in data:
        client.email = data["email"]
    if "teams_email" in data:
        client.teams_email = data["teams_email"]
    if "check_interval" in data:
        client.check_interval = int(data["check_interval"])
    if "smtp_email" in data:
        client.smtp_email = data["smtp_email"]
    if "notification_email" in data:
        client.notification_email = data["notification_email"]
    if "whatsapp" in data:
        client.whatsapp = data["whatsapp"]
    if "plan_id" in data:
        client.plan_id = data["plan_id"]

    # Campos criptografados (so atualiza se enviou valor nao vazio)
    if data.get("teams_password"):
        client.teams_password = data["teams_password"]
    if data.get("anthropic_key"):
        client.anthropic_key = data["anthropic_key"]
    if data.get("smtp_password"):
        client.smtp_password = data["smtp_password"]

    db.session.commit()

    # Re-agendar se mudou intervalo
    if "check_interval" in data:
        try:
            from engine.scheduler import agendar_cliente
            agendar_cliente(client)
        except Exception:
            pass

    return jsonify(client_to_dict(client))


# ============================================
# DELETE
# ============================================

@api_clients_bp.route("/<int:client_id>", methods=["DELETE"])
@jwt_or_session_required
def delete_client(client_id):
    """Remove cliente e dados associados."""
    client = Client.query.get_or_404(client_id)

    # Remover do scheduler
    try:
        from engine.scheduler import remover_cliente
        remover_cliente(client.id)
    except Exception:
        pass

    # Remover registros associados
    TaskLog.query.filter_by(client_id=client_id).delete()
    Payment.query.filter_by(client_id=client_id).delete()
    ClientStatus.query.filter_by(client_id=client_id).delete()
    db.session.delete(client)
    db.session.commit()

    return jsonify({"message": f"Cliente {client.nome} removido"})


# ============================================
# TOGGLE (pausar/ativar)
# ============================================

@api_clients_bp.route("/<int:client_id>/toggle", methods=["POST"])
@jwt_or_session_required
def toggle_client(client_id):
    """Pausa ou ativa cliente."""
    client = Client.query.get_or_404(client_id)

    if client.status == "paused":
        client.status = "active"
        try:
            from engine.scheduler import agendar_cliente
            agendar_cliente(client)
        except Exception:
            pass
    else:
        client.status = "paused"
        try:
            from engine.scheduler import remover_cliente
            remover_cliente(client.id)
        except Exception:
            pass

    db.session.commit()
    return jsonify(client_to_dict(client))


# ============================================
# RUN NOW
# ============================================

@api_clients_bp.route("/<int:client_id>/run", methods=["POST"])
@jwt_or_session_required
def run_client(client_id):
    """Executa monitoramento do cliente imediatamente."""
    client = Client.query.get_or_404(client_id)

    if not client.is_active and client.status != "paused":
        return jsonify({"error": "Cliente expirado"}), 400

    try:
        from engine.scheduler import run_client_now
        run_client_now(client.id)
        return jsonify({"message": f"Execucao iniciada para {client.nome}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# RENEW
# ============================================

@api_clients_bp.route("/<int:client_id>/renew", methods=["POST"])
@jwt_or_session_required
def renew_client(client_id):
    """Renova assinatura do cliente."""
    client = Client.query.get_or_404(client_id)
    data = request.get_json(silent=True) or {}

    months = data.get("months", 1)
    if not isinstance(months, int) or months < 1:
        months = 1

    amount = data.get("amount", 0)

    client.renew(months)

    if amount and float(amount) > 0:
        payment = Payment(
            client_id=client.id,
            amount=float(amount),
            months=months,
        )
        db.session.add(payment)

    db.session.commit()

    # Re-agendar
    try:
        from engine.scheduler import agendar_cliente
        agendar_cliente(client)
    except Exception:
        pass

    return jsonify(client_to_dict(client))


# ============================================
# RUN ALL
# ============================================

@api_clients_bp.route("/run-all", methods=["POST"])
@jwt_or_session_required
def run_all_clients():
    """Executa todos os clientes ativos."""
    clients = Client.query.filter_by(status="active").all()
    active = [c for c in clients if c.is_active]

    started = 0
    for client in active:
        try:
            from engine.scheduler import run_client_now
            run_client_now(client.id)
            started += 1
        except Exception:
            pass

    return jsonify({
        "message": f"Execucao iniciada para {started} clientes",
        "started": started,
        "total_active": len(active),
    })
