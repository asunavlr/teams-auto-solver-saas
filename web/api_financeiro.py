"""API de dados financeiros e relatórios."""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from sqlalchemy import func

from web import db
from web.models import Client, Plan, Payment, ApiCost, TaskLog
from web.api_auth import jwt_or_session_required

api_financeiro_bp = Blueprint("api_financeiro", __name__, url_prefix="/api/financeiro")


@api_financeiro_bp.route("/resumo")
@jwt_or_session_required
def resumo():
    """Retorna resumo financeiro geral."""
    now = datetime.utcnow()
    inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Receita do mês (pagamentos)
    receita_mes = db.session.query(func.sum(Payment.amount)).filter(
        Payment.created_at >= inicio_mes
    ).scalar() or 0.0

    # Receita total
    receita_total = db.session.query(func.sum(Payment.amount)).scalar() or 0.0

    # Custos do mês (API)
    custos_mes = ApiCost.custo_total_mes()

    # Custos total
    custos_total = db.session.query(func.sum(ApiCost.custo)).scalar() or 0.0

    # Lucro
    lucro_mes = receita_mes - custos_mes
    lucro_total = receita_total - custos_total

    # Clientes por status
    total_clientes = Client.query.count()
    clientes_ativos = Client.query.filter(
        Client.status == "active",
        Client.expires_at > now
    ).count()
    clientes_expirados = Client.query.filter(Client.expires_at <= now).count()
    clientes_pausados = Client.query.filter(Client.status == "paused").count()

    # Clientes por plano
    clientes_por_plano = []
    planos = Plan.query.all()
    for plano in planos:
        count = Client.query.filter_by(plan_id=plano.id).count()
        clientes_por_plano.append({
            "plano": plano.nome,
            "preco": plano.preco_mensal,
            "quantidade": count,
            "receita_potencial": count * plano.preco_mensal
        })

    # Tarefas do mês
    tarefas_mes = TaskLog.query.filter(TaskLog.created_at >= inicio_mes).count()
    tarefas_sucesso = TaskLog.query.filter(
        TaskLog.created_at >= inicio_mes,
        TaskLog.status == "success"
    ).count()

    return jsonify({
        "receita": {
            "mes": round(receita_mes, 2),
            "total": round(receita_total, 2),
        },
        "custos": {
            "mes": round(custos_mes, 2),
            "total": round(custos_total, 2),
        },
        "lucro": {
            "mes": round(lucro_mes, 2),
            "total": round(lucro_total, 2),
        },
        "clientes": {
            "total": total_clientes,
            "ativos": clientes_ativos,
            "expirados": clientes_expirados,
            "pausados": clientes_pausados,
        },
        "clientes_por_plano": clientes_por_plano,
        "tarefas": {
            "mes": tarefas_mes,
            "sucesso": tarefas_sucesso,
        },
        "margem_lucro": round((lucro_mes / receita_mes * 100) if receita_mes > 0 else 100, 1),
    })


@api_financeiro_bp.route("/clientes")
@jwt_or_session_required
def clientes_financeiro():
    """Retorna dados financeiros de cada cliente."""
    now = datetime.utcnow()
    inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    clientes = Client.query.all()
    result = []

    for client in clientes:
        # Pagamentos do cliente
        pagamentos_total = db.session.query(func.sum(Payment.amount)).filter(
            Payment.client_id == client.id
        ).scalar() or 0.0

        ultimo_pagamento = Payment.query.filter_by(client_id=client.id)\
            .order_by(Payment.created_at.desc()).first()

        # Custos do cliente
        custos_mes = ApiCost.custo_cliente_mes(client.id)
        custos_total = db.session.query(func.sum(ApiCost.custo)).filter(
            ApiCost.client_id == client.id
        ).scalar() or 0.0

        # Tarefas
        tarefas_total = TaskLog.query.filter_by(client_id=client.id).count()
        tarefas_sucesso = TaskLog.query.filter_by(client_id=client.id, status="success").count()

        # Preço do plano
        preco_plano = client.plan.preco_mensal if client.plan else 0

        # Lucro estimado
        lucro_estimado = preco_plano - custos_mes

        result.append({
            "id": client.id,
            "nome": client.nome,
            "email": client.email,
            "plano": client.plan.nome if client.plan else "Sem plano",
            "preco_plano": preco_plano,
            "status": "ativo" if client.is_active else ("pausado" if client.status == "paused" else "expirado"),
            "dias_restantes": client.days_remaining,
            "expires_at": client.expires_at.isoformat() if client.expires_at else None,
            "pagamentos_total": round(pagamentos_total, 2),
            "ultimo_pagamento": ultimo_pagamento.created_at.isoformat() if ultimo_pagamento else None,
            "ultimo_valor": ultimo_pagamento.amount if ultimo_pagamento else 0,
            "custos_mes": round(custos_mes, 2),
            "custos_total": round(custos_total, 2),
            "lucro_estimado": round(lucro_estimado, 2),
            "tarefas_total": tarefas_total,
            "tarefas_sucesso": tarefas_sucesso,
            "taxa_sucesso": round((tarefas_sucesso / tarefas_total * 100) if tarefas_total > 0 else 0, 1),
            "created_at": client.created_at.isoformat() if client.created_at else None,
        })

    # Ordena por lucro estimado (maior primeiro)
    result.sort(key=lambda x: x["lucro_estimado"], reverse=True)

    return jsonify(result)


@api_financeiro_bp.route("/pagamentos")
@jwt_or_session_required
def pagamentos():
    """Retorna histórico de pagamentos."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    client_id = request.args.get("client_id", type=int)

    query = Payment.query.join(Client)

    if client_id:
        query = query.filter(Payment.client_id == client_id)

    query = query.order_by(Payment.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [{
            "id": p.id,
            "client_id": p.client_id,
            "client_nome": p.client.nome,
            "amount": p.amount,
            "months": p.months,
            "created_at": p.created_at.isoformat(),
        } for p in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
    })


@api_financeiro_bp.route("/custos")
@jwt_or_session_required
def custos():
    """Retorna histórico de custos de API."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    client_id = request.args.get("client_id", type=int)
    tipo = request.args.get("tipo")

    query = ApiCost.query.join(Client)

    if client_id:
        query = query.filter(ApiCost.client_id == client_id)
    if tipo:
        query = query.filter(ApiCost.tipo == tipo)

    query = query.order_by(ApiCost.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [{
            "id": c.id,
            "client_id": c.client_id,
            "client_nome": c.client.nome,
            "tipo": c.tipo,
            "custo": c.custo,
            "descricao": c.descricao,
            "created_at": c.created_at.isoformat(),
        } for c in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
    })


@api_financeiro_bp.route("/receita-mensal")
@jwt_or_session_required
def receita_mensal():
    """Retorna receita dos últimos 6 meses."""
    now = datetime.utcnow()
    meses = []

    for i in range(5, -1, -1):
        # Calcula início e fim do mês
        mes = now.month - i
        ano = now.year
        while mes <= 0:
            mes += 12
            ano -= 1

        inicio = datetime(ano, mes, 1)
        if mes == 12:
            fim = datetime(ano + 1, 1, 1)
        else:
            fim = datetime(ano, mes + 1, 1)

        # Receita do mês
        receita = db.session.query(func.sum(Payment.amount)).filter(
            Payment.created_at >= inicio,
            Payment.created_at < fim
        ).scalar() or 0.0

        # Custos do mês
        custos = db.session.query(func.sum(ApiCost.custo)).filter(
            ApiCost.created_at >= inicio,
            ApiCost.created_at < fim
        ).scalar() or 0.0

        meses.append({
            "mes": inicio.strftime("%b/%y"),
            "receita": round(receita, 2),
            "custos": round(custos, 2),
            "lucro": round(receita - custos, 2),
        })

    return jsonify(meses)
