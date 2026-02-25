"""Modelos do banco de dados."""

from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from web import db
import config as cfg


def _get_fernet():
    key = cfg.ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY nao configurada no .env")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().decrypt(value.encode()).decode()


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    teams_email = db.Column(db.String(200), nullable=False)
    _teams_password = db.Column("teams_password", db.Text, nullable=False)
    _anthropic_key = db.Column("anthropic_key", db.Text, nullable=False)
    smtp_email = db.Column(db.String(200), default="")
    _smtp_password = db.Column("smtp_password", db.Text, default="")
    notification_email = db.Column(db.String(200), default="")
    status = db.Column(db.String(20), default="active")
    expires_at = db.Column(db.DateTime, nullable=False)
    check_interval = db.Column(db.Integer, default=60)
    last_check = db.Column(db.DateTime)
    tasks_completed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task_logs = db.relationship("TaskLog", backref="client", lazy="dynamic")
    payments = db.relationship("Payment", backref="client", lazy="dynamic")

    @property
    def teams_password(self):
        return decrypt_value(self._teams_password)

    @teams_password.setter
    def teams_password(self, value):
        self._teams_password = encrypt_value(value)

    @property
    def anthropic_key(self):
        return decrypt_value(self._anthropic_key)

    @anthropic_key.setter
    def anthropic_key(self, value):
        self._anthropic_key = encrypt_value(value)

    @property
    def smtp_password(self):
        return decrypt_value(self._smtp_password)

    @smtp_password.setter
    def smtp_password(self, value):
        self._smtp_password = encrypt_value(value)

    @property
    def is_active(self):
        return self.status == "active" and self.expires_at > datetime.utcnow()

    @property
    def is_expired(self):
        return self.expires_at <= datetime.utcnow()

    @property
    def days_remaining(self):
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def data_dir(self):
        path = cfg.DATA_DIR / f"client_{self.id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def renew(self, months: int):
        base = max(self.expires_at, datetime.utcnow())
        self.expires_at = base + timedelta(days=30 * months)
        self.status = "active"


class TaskLog(db.Model):
    __tablename__ = "task_logs"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    task_name = db.Column(db.String(300), nullable=False)
    discipline = db.Column(db.String(200), default="")
    format = db.Column(db.String(20), default="")
    status = db.Column(db.String(20), default="success")
    error_msg = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    months = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
