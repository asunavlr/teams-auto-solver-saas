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


class Plan(db.Model):
    """Planos de assinatura."""
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)  # Trial, Básico, Premium, Ilimitado
    preco_mensal = db.Column(db.Float, nullable=False)
    preco_semestral = db.Column(db.Float, nullable=False)
    limite_tarefas = db.Column(db.Integer, nullable=True)  # None = ilimitado
    is_trial = db.Column(db.Boolean, default=False)  # Trial não reseta mensalmente
    duracao_dias = db.Column(db.Integer, nullable=True)  # Duração fixa (para trial)
    ativo = db.Column(db.Boolean, default=True)

    @classmethod
    def seed_plans(cls):
        """Cria planos padrão se não existirem."""
        plans_data = [
            {"nome": "Trial", "preco_mensal": 0, "preco_semestral": 0, "limite_tarefas": 3, "is_trial": True, "duracao_dias": 7},
            {"nome": "Básico", "preco_mensal": 60, "preco_semestral": 300, "limite_tarefas": 60},
            {"nome": "Premium", "preco_mensal": 100, "preco_semestral": 500, "limite_tarefas": 120},
            {"nome": "Ilimitado", "preco_mensal": 150, "preco_semestral": 750, "limite_tarefas": None},
        ]
        for data in plans_data:
            if not cls.query.filter_by(nome=data["nome"]).first():
                db.session.add(cls(**data))
        db.session.commit()


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
    whatsapp = db.Column(db.String(20), default="")
    status = db.Column(db.String(20), default="active")
    expires_at = db.Column(db.DateTime, nullable=False)
    check_interval = db.Column(db.Integer, default=60)
    last_check = db.Column(db.DateTime)
    tasks_completed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Plano e controle de uso
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=True)
    tarefas_mes = db.Column(db.Integer, default=0)  # Contador do mês atual
    mes_contagem = db.Column(db.Integer, default=0)  # Mês do contador (1-12)
    used_trial = db.Column(db.Boolean, default=False)  # Já usou trial

    plan = db.relationship("Plan", backref="clients")
    task_logs = db.relationship("TaskLog", backref="client", lazy="dynamic")
    payments = db.relationship("Payment", backref="client", lazy="dynamic")

    def verificar_reset_mensal(self):
        """Reseta contador se mudou o mês (exceto para trial)."""
        # Trial não reseta - limite é total, não mensal
        if self.plan and self.plan.is_trial:
            return
        mes_atual = datetime.utcnow().month
        if self.mes_contagem != mes_atual:
            self.tarefas_mes = 0
            self.mes_contagem = mes_atual
            db.session.commit()

    def incrementar_tarefa(self):
        """Incrementa contador de tarefas do mês."""
        self.verificar_reset_mensal()
        self.tarefas_mes += 1
        self.tasks_completed += 1
        db.session.commit()

    @property
    def limite_tarefas(self):
        """Retorna limite de tarefas do plano."""
        if self.plan:
            return self.plan.limite_tarefas
        return None  # Sem plano = sem limite (legado)

    @property
    def tarefas_restantes(self):
        """Retorna quantas tarefas ainda pode fazer este mês."""
        self.verificar_reset_mensal()
        if self.limite_tarefas is None:
            return None  # Ilimitado
        return max(0, self.limite_tarefas - self.tarefas_mes)

    @property
    def limite_atingido(self):
        """Verifica se atingiu o limite de tarefas."""
        if self.limite_tarefas is None:
            return False
        self.verificar_reset_mensal()
        return self.tarefas_mes >= self.limite_tarefas

    @property
    def uso_percentual(self):
        """Retorna percentual de uso do plano."""
        if self.limite_tarefas is None or self.limite_tarefas == 0:
            return 0
        self.verificar_reset_mensal()
        return min(100, int((self.tarefas_mes / self.limite_tarefas) * 100))

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
    def is_trial(self):
        """Verifica se está no plano trial."""
        return self.plan and self.plan.is_trial

    @property
    def can_use_trial(self):
        """Verifica se pode usar trial (nunca usou antes)."""
        return not self.used_trial

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

    def activate_trial(self):
        """Ativa o plano trial para o cliente. Retorna True se sucesso, False se já usou."""
        if self.used_trial:
            return False
        trial_plan = Plan.query.filter_by(is_trial=True).first()
        if not trial_plan:
            return False
        self.plan_id = trial_plan.id
        self.used_trial = True
        self.tarefas_mes = 0  # Reseta contador
        self.expires_at = datetime.utcnow() + timedelta(days=trial_plan.duracao_dias or 7)
        self.status = "active"
        db.session.commit()
        return True


class TaskLog(db.Model):
    __tablename__ = "task_logs"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    task_name = db.Column(db.String(300), nullable=False)
    discipline = db.Column(db.String(200), default="")
    format = db.Column(db.String(20), default="")
    status = db.Column(db.String(50), default="success")
    error_msg = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Detalhes da tarefa
    instrucoes = db.Column(db.Text, default="")  # Instrucoes originais da tarefa
    resposta = db.Column(db.Text, default="")  # Resposta gerada pelo Claude
    arquivos_enviados = db.Column(db.Text, default="")  # JSON com lista de arquivos

    # Debug info (JSON com screenshot base64, url, frames, etc)
    debug_data = db.Column(db.Text, default="")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    months = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClientStatus(db.Model):
    """Status em tempo real de cada cliente."""
    __tablename__ = "client_status"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, unique=True)
    status = db.Column(db.String(20), default="idle")  # idle, running, error
    current_action = db.Column(db.String(300), default="")  # descricao do que esta fazendo
    started_at = db.Column(db.DateTime)
    last_error = db.Column(db.Text, default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = db.relationship("Client", backref=db.backref("runtime_status", uselist=False))

    @classmethod
    def set_status(cls, client_id: int, status: str, action: str = "", error: str = ""):
        """Atualiza status do cliente."""
        obj = cls.query.filter_by(client_id=client_id).first()
        if not obj:
            obj = cls(client_id=client_id)
            db.session.add(obj)

        obj.status = status
        obj.current_action = action
        if status == "running" and not obj.started_at:
            obj.started_at = datetime.utcnow()
        elif status == "idle":
            obj.started_at = None
        if error:
            obj.last_error = error

        db.session.commit()
        return obj

    @classmethod
    def get_status(cls, client_id: int):
        """Retorna status do cliente."""
        obj = cls.query.filter_by(client_id=client_id).first()
        if obj:
            return {
                "status": obj.status,
                "current_action": obj.current_action,
                "started_at": obj.started_at,
                "last_error": obj.last_error
            }
        return {"status": "idle", "current_action": "", "started_at": None, "last_error": ""}


class ApiCost(db.Model):
    """Rastreamento de custos de API (Vision, Claude, etc)."""
    __tablename__ = "api_costs"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # vision, claude_task, etc
    custo = db.Column(db.Float, default=0.0)  # em BRL
    descricao = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship("Client", backref=db.backref("api_costs", lazy="dynamic"))

    @classmethod
    def registrar(cls, client_id: int, tipo: str, custo: float, descricao: str = ""):
        """Registra um custo de API."""
        obj = cls(
            client_id=client_id,
            tipo=tipo,
            custo=custo,
            descricao=descricao
        )
        db.session.add(obj)
        db.session.commit()
        return obj

    @classmethod
    def custo_cliente_mes(cls, client_id: int) -> float:
        """Retorna custo total do cliente no mês atual."""
        inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total = db.session.query(db.func.sum(cls.custo)).filter(
            cls.client_id == client_id,
            cls.created_at >= inicio_mes
        ).scalar()
        return total or 0.0

    @classmethod
    def custo_total_mes(cls) -> float:
        """Retorna custo total de todos os clientes no mês atual."""
        inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total = db.session.query(db.func.sum(cls.custo)).filter(
            cls.created_at >= inicio_mes
        ).scalar()
        return total or 0.0
