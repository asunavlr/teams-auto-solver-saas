"""
Script para adicionar colunas do plano Trial.

Rode uma vez para atualizar o banco de dados:
    python scripts/add_trial_columns.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # Adiciona colunas na tabela plans
    try:
        db.session.execute(text("ALTER TABLE plans ADD COLUMN is_trial BOOLEAN DEFAULT FALSE"))
        print("Coluna 'is_trial' adicionada em plans")
    except Exception as e:
        print(f"Coluna 'is_trial' ja existe ou erro: {e}")

    try:
        db.session.execute(text("ALTER TABLE plans ADD COLUMN duracao_dias INTEGER"))
        print("Coluna 'duracao_dias' adicionada em plans")
    except Exception as e:
        print(f"Coluna 'duracao_dias' ja existe ou erro: {e}")

    # Adiciona coluna na tabela clients
    try:
        db.session.execute(text("ALTER TABLE clients ADD COLUMN used_trial BOOLEAN DEFAULT FALSE"))
        print("Coluna 'used_trial' adicionada em clients")
    except Exception as e:
        print(f"Coluna 'used_trial' ja existe ou erro: {e}")

    db.session.commit()

    # Cria o plano Trial se não existir
    from web.models import Plan
    trial = Plan.query.filter_by(nome="Trial").first()
    if not trial:
        trial = Plan(
            nome="Trial",
            preco_mensal=0,
            preco_semestral=0,
            limite_tarefas=3,
            is_trial=True,
            duracao_dias=7,
            ativo=True
        )
        db.session.add(trial)
        db.session.commit()
        print("Plano Trial criado com sucesso!")
    else:
        # Atualiza valores se já existe
        trial.is_trial = True
        trial.duracao_dias = 7
        trial.limite_tarefas = 3
        db.session.commit()
        print("Plano Trial atualizado!")

    print("\nMigracao concluida!")
