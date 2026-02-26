"""API de autenticacao JWT."""

from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, jsonify, request, g
from flask_login import current_user, login_required as session_required

import config as cfg

api_auth_bp = Blueprint("api_auth", __name__, url_prefix="/api/auth")

# Tokens invalidados (em producao usar Redis)
_blacklisted_tokens = set()


def generate_token(username: str) -> str:
    """Gera JWT token."""
    payload = {
        "sub": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=cfg.JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, cfg.JWT_SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    """Decodifica JWT token. Retorna payload ou None."""
    try:
        if token in _blacklisted_tokens:
            return None
        payload = jwt.decode(token, cfg.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def jwt_or_session_required(f):
    """Decorator que aceita autenticacao via JWT OU sessao Flask-Login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. Tenta JWT via header Authorization
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_token(token)
            if payload:
                g.current_user = payload["sub"]
                return f(*args, **kwargs)
            return jsonify({"error": "Token invalido ou expirado"}), 401

        # 2. Fallback pra sessao Flask-Login (Jinja2 antigo)
        if current_user.is_authenticated:
            g.current_user = "admin"
            return f(*args, **kwargs)

        return jsonify({"error": "Autenticacao necessaria"}), 401
    return decorated


# ============================================
# ENDPOINTS
# ============================================

@api_auth_bp.route("/login", methods=["POST"])
def login():
    """Login via JSON, retorna JWT."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if username == cfg.ADMIN_USERNAME and password == cfg.ADMIN_PASSWORD:
        token = generate_token(username)
        return jsonify({
            "token": token,
            "user": {
                "username": username,
                "role": "admin",
            },
            "expires_in": cfg.JWT_EXPIRATION_HOURS * 3600,
        })

    return jsonify({"error": "Usuario ou senha incorretos"}), 401


@api_auth_bp.route("/logout", methods=["POST"])
def logout():
    """Invalida o token JWT atual."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        _blacklisted_tokens.add(token)
        # Limpa tokens muito antigos pra nao crescer infinito
        if len(_blacklisted_tokens) > 1000:
            _blacklisted_tokens.clear()
    return jsonify({"message": "Logout realizado"})


@api_auth_bp.route("/me")
@jwt_or_session_required
def me():
    """Retorna dados do usuario autenticado."""
    return jsonify({
        "username": g.current_user,
        "role": "admin",
    })
