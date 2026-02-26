"""API de planos."""

from flask import Blueprint, jsonify

from web.models import Plan
from web.api_auth import jwt_or_session_required

api_plans_bp = Blueprint("api_plans", __name__, url_prefix="/api/plans")


@api_plans_bp.route("")
@jwt_or_session_required
def list_plans():
    """Lista planos ativos."""
    plans = Plan.query.filter_by(ativo=True).all()

    return jsonify([{
        "id": p.id,
        "nome": p.nome,
        "preco_mensal": p.preco_mensal,
        "preco_semestral": p.preco_semestral,
        "limite_tarefas": p.limite_tarefas,
    } for p in plans])
