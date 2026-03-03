"""Fixtures compartilhados para testes."""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Garante que o diretorio raiz do projeto esta no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _gerar_fernet_key():
    """Gera uma chave Fernet valida para testes."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# Configura env vars ANTES de importar qualquer modulo do projeto
os.environ.setdefault("DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ENCRYPTION_KEY", _gerar_fernet_key())
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("TIMEZONE", "America/Sao_Paulo")


@pytest.fixture()
def app():
    """Cria app Flask de teste com banco in-memory (sem pool_size pro SQLite)."""

    # Mock do scheduler para evitar imports de engine
    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.get_job.return_value = None

    with patch.dict("sys.modules", {
        "engine": MagicMock(),
        "engine.scheduler": MagicMock(
            scheduler=mock_scheduler,
            get_queue_status=lambda: {},
        ),
    }):
        from flask import Flask
        from flask_cors import CORS
        from web import db, login_manager

        app = Flask(__name__)
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["TESTING"] = True
        # Sem pool_size/max_overflow — SQLite in-memory nao suporta

        db.init_app(app)
        login_manager.init_app(app)
        login_manager.login_view = "auth.login"

        CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

        # Registra blueprints
        from web.auth import auth_bp
        from web.routes import main_bp
        from web.api import api_bp
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
            db.create_all()
            from web.models import Plan
            Plan.seed_plans()

        yield app

        with app.app_context():
            db.session.remove()
            db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client com autenticacao JWT."""
    from web.api_auth import generate_token

    token = generate_token("admin")
    test_client = app.test_client()

    class AuthClient:
        """Wrapper que injeta JWT em todas as requests."""
        def __init__(self, tc, tk):
            self._client = tc
            self._headers = {"Authorization": f"Bearer {tk}"}

        def get(self, *args, **kwargs):
            kwargs.setdefault("headers", {}).update(self._headers)
            return self._client.get(*args, **kwargs)

        def post(self, *args, **kwargs):
            kwargs.setdefault("headers", {}).update(self._headers)
            return self._client.post(*args, **kwargs)

    return AuthClient(test_client, token)


@pytest.fixture()
def seed_data(app):
    """Cria dados de teste: 1 cliente + 3 task logs + status."""
    from web import db
    from web.models import Client, TaskLog, ClientStatus

    with app.app_context():
        cliente = Client(
            nome="Teste Silva",
            email="teste@example.com",
            teams_email="teste@teams.com",
            teams_password="fake-password",
            anthropic_key="sk-fake-key",
            status="active",
            expires_at=datetime.utcnow() + timedelta(days=30),
            last_check=datetime.utcnow() - timedelta(minutes=45),
            check_interval=60,
            tasks_completed=3,
        )
        db.session.add(cliente)
        db.session.flush()

        # Task logs com timestamps variados
        for i, (name, status) in enumerate([
            ("Atividade Calculo", "success"),
            ("Atividade Fisica", "success"),
            ("Atividade Quimica", "error"),
        ]):
            log = TaskLog(
                client_id=cliente.id,
                task_name=name,
                discipline="Disciplina",
                format="docx",
                status=status,
                error_msg="timeout" if status == "error" else "",
                created_at=datetime.utcnow() - timedelta(hours=i),
            )
            db.session.add(log)

        # Status runtime
        cs = ClientStatus(
            client_id=cliente.id,
            status="idle",
            started_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(cs)

        db.session.commit()

        return {"client_id": cliente.id}
