"""Flask app factory."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

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

    from web.auth import auth_bp
    from web.routes import main_bp
    from web.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        from web import models  # noqa: F401
        from web.models import Plan
        db.create_all()
        Plan.seed_plans()  # Cria planos padrão

    return app
