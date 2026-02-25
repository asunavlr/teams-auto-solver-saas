#!/usr/bin/env python3
"""
Script para migrar dados do SQLite para Supabase (PostgreSQL).

Uso:
    python scripts/migrate_to_supabase.py

Requer:
    - DATABASE_URI configurado no .env apontando para Supabase
    - Banco SQLite em instance/database.db
"""

import os
import sys
import sqlite3
from datetime import datetime

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def migrate():
    """Migra dados do SQLite para PostgreSQL (Supabase)."""

    # Verifica se DATABASE_URI aponta para PostgreSQL
    database_uri = os.getenv("DATABASE_URI", "")
    if not database_uri.startswith("postgresql"):
        print("ERRO: DATABASE_URI deve apontar para PostgreSQL (Supabase)")
        print(f"Atual: {database_uri[:50]}...")
        print("\nConfigure no .env:")
        print("DATABASE_URI=postgresql://postgres:[SENHA]@db.[PROJETO].supabase.co:5432/postgres")
        sys.exit(1)

    # Conecta ao SQLite
    sqlite_path = "instance/database.db"
    if not os.path.exists(sqlite_path):
        print(f"ERRO: Banco SQLite nao encontrado em {sqlite_path}")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    print("=" * 50)
    print("MIGRACAO SQLite -> Supabase")
    print("=" * 50)

    # Cria app Flask para contexto
    from web import create_app, db
    app = create_app()

    with app.app_context():
        # Cria tabelas no PostgreSQL
        print("\n1. Criando tabelas no Supabase...")
        db.create_all()
        print("   OK - Tabelas criadas")

        # Migra Plans
        print("\n2. Migrando planos...")
        sqlite_cursor.execute("SELECT * FROM plans")
        plans = sqlite_cursor.fetchall()

        from web.models import Plan
        for plan in plans:
            existing = Plan.query.filter_by(nome=plan["nome"]).first()
            if not existing:
                new_plan = Plan(
                    id=plan["id"],
                    nome=plan["nome"],
                    preco_mensal=plan["preco_mensal"],
                    preco_semestral=plan["preco_semestral"],
                    limite_tarefas=plan["limite_tarefas"],
                    ativo=bool(plan["ativo"]) if plan["ativo"] is not None else True
                )
                db.session.add(new_plan)
        db.session.commit()
        print(f"   OK - {len(plans)} plano(s) migrado(s)")

        # Migra Clients
        print("\n3. Migrando clientes...")
        sqlite_cursor.execute("SELECT * FROM clients")
        clients = sqlite_cursor.fetchall()

        from web.models import Client
        for client in clients:
            existing = Client.query.get(client["id"])
            if not existing:
                new_client = Client(
                    id=client["id"],
                    nome=client["nome"],
                    email=client["email"],
                    teams_email=client["teams_email"],
                    _teams_password=client["teams_password"],
                    _anthropic_key=client["anthropic_key"],
                    smtp_email=client["smtp_email"] or "",
                    _smtp_password=client["smtp_password"] or "",
                    notification_email=client["notification_email"] or "",
                    whatsapp=client["whatsapp"] if "whatsapp" in client.keys() else "",
                    status=client["status"],
                    expires_at=datetime.fromisoformat(client["expires_at"]) if client["expires_at"] else None,
                    check_interval=client["check_interval"],
                    last_check=datetime.fromisoformat(client["last_check"]) if client["last_check"] else None,
                    tasks_completed=client["tasks_completed"] or 0,
                    created_at=datetime.fromisoformat(client["created_at"]) if client["created_at"] else datetime.utcnow(),
                    plan_id=client["plan_id"] if "plan_id" in client.keys() else None,
                    tarefas_mes=client["tarefas_mes"] if "tarefas_mes" in client.keys() else 0,
                    mes_contagem=client["mes_contagem"] if "mes_contagem" in client.keys() else 0,
                )
                db.session.add(new_client)
        db.session.commit()
        print(f"   OK - {len(clients)} cliente(s) migrado(s)")

        # Migra TaskLogs
        print("\n4. Migrando logs de tarefas...")
        sqlite_cursor.execute("SELECT * FROM task_logs")
        logs = sqlite_cursor.fetchall()

        from web.models import TaskLog
        batch_size = 100
        for i in range(0, len(logs), batch_size):
            batch = logs[i:i + batch_size]
            for log in batch:
                existing = TaskLog.query.get(log["id"])
                if not existing:
                    new_log = TaskLog(
                        id=log["id"],
                        client_id=log["client_id"],
                        task_name=log["task_name"],
                        discipline=log["discipline"] or "",
                        format=log["format"] or "",
                        status=log["status"],
                        error_msg=log["error_msg"] or "",
                        created_at=datetime.fromisoformat(log["created_at"]) if log["created_at"] else datetime.utcnow(),
                    )
                    db.session.add(new_log)
            db.session.commit()
            print(f"   ... {min(i + batch_size, len(logs))}/{len(logs)}")
        print(f"   OK - {len(logs)} log(s) migrado(s)")

        # Migra Payments
        print("\n5. Migrando pagamentos...")
        sqlite_cursor.execute("SELECT * FROM payments")
        payments = sqlite_cursor.fetchall()

        from web.models import Payment
        for payment in payments:
            existing = Payment.query.get(payment["id"])
            if not existing:
                new_payment = Payment(
                    id=payment["id"],
                    client_id=payment["client_id"],
                    amount=payment["amount"],
                    months=payment["months"],
                    created_at=datetime.fromisoformat(payment["created_at"]) if payment["created_at"] else datetime.utcnow(),
                )
                db.session.add(new_payment)
        db.session.commit()
        print(f"   OK - {len(payments)} pagamento(s) migrado(s)")

        # Migra ClientStatus (se existir)
        print("\n6. Migrando status de clientes...")
        try:
            sqlite_cursor.execute("SELECT * FROM client_status")
            statuses = sqlite_cursor.fetchall()

            from web.models import ClientStatus
            for status in statuses:
                existing = ClientStatus.query.filter_by(client_id=status["client_id"]).first()
                if not existing:
                    new_status = ClientStatus(
                        client_id=status["client_id"],
                        status=status["status"],
                        current_action=status["current_action"] or "",
                        last_error=status["last_error"] or "",
                    )
                    db.session.add(new_status)
            db.session.commit()
            print(f"   OK - {len(statuses)} status migrado(s)")
        except Exception as e:
            print(f"   Tabela client_status nao encontrada ou vazia: {e}")

    sqlite_conn.close()

    print("\n" + "=" * 50)
    print("MIGRACAO CONCLUIDA COM SUCESSO!")
    print("=" * 50)
    print("\nProximos passos:")
    print("1. Verifique os dados no Supabase Dashboard")
    print("2. Atualize o .env no VPS com DATABASE_URI do Supabase")
    print("3. Faca deploy com: docker compose up -d")


if __name__ == "__main__":
    migrate()
