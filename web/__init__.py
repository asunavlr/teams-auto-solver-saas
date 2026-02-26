"""Flask app factory."""

import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_cors import CORS

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = __import__("config").SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = __import__("config").DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Limita conexoes para evitar MaxClients no Supabase
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 2,
        "max_overflow": 3,
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faca login para acessar o painel."

    # CORS para desenvolvimento (Vite em localhost:5173)
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    # Blueprints existentes
    from web.auth import auth_bp
    from web.routes import main_bp
    from web.api import api_bp

    # Novos blueprints API
    from web.api_auth import api_auth_bp
    from web.api_clients import api_clients_bp
    from web.api_plans import api_plans_bp
    from web.api_logs import api_logs_bp
    from web.api_financeiro import api_financeiro_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(api_auth_bp)
    app.register_blueprint(api_clients_bp)
    app.register_blueprint(api_plans_bp)
    app.register_blueprint(api_logs_bp)
    app.register_blueprint(api_financeiro_bp)

    with app.app_context():
        from web import models  # noqa: F401
        from web.models import Plan
        db.create_all()
        Plan.seed_plans()  # Cria planos padrao

    # Servir React build em producao
    # Se frontend/dist existe, serve como SPA (Single Page Application)
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

    if frontend_dist.exists():
        @app.route("/app/", defaults={"path": ""})
        @app.route("/app/<path:path>")
        def serve_react(path):
            """Serve o frontend React."""
            file_path = frontend_dist / path
            if path and file_path.exists():
                return send_from_directory(str(frontend_dist), path)
            return send_from_directory(str(frontend_dist), "index.html")

    return app
