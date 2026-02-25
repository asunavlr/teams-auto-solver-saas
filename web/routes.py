"""Rotas do painel web."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required

import config as cfg
from web import db
from web.models import Client, TaskLog, Payment, Plan

main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
def health():
    """Health check simples (sem autenticacao) para Docker/monitoring."""
    from flask import jsonify
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


def get_today_start():
    """Retorna inicio do dia no fuso horario local."""
    try:
        tz = ZoneInfo(cfg.TIMEZONE)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now(timezone(timedelta(hours=-3)))
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


@main_bp.route("/")
@login_required
def dashboard():
    today_start = get_today_start()
    all_clients = Client.query.all()

    stats = {
        "total_clients": len(all_clients),
        "active_clients": sum(1 for c in all_clients if c.is_active),
        "expired_clients": sum(1 for c in all_clients if c.is_expired),
        "tasks_today": TaskLog.query.filter(
            TaskLog.created_at >= today_start
        ).count(),
    }

    expiring_clients = [
        c for c in all_clients
        if c.is_active and 0 < c.days_remaining <= 7
    ]

    recent_tasks = TaskLog.query.order_by(TaskLog.created_at.desc()).limit(10).all()
    recent_clients = Client.query.order_by(Client.created_at.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        stats=stats,
        expiring_clients=expiring_clients,
        recent_tasks=recent_tasks,
        recent_clients=recent_clients,
    )


@main_bp.route("/clients")
@login_required
def clients():
    filter_type = request.args.get("filter", "")

    query = Client.query.order_by(Client.created_at.desc())
    if filter_type == "active":
        query = query.filter(Client.status == "active", Client.expires_at > datetime.utcnow())
    elif filter_type == "expired":
        query = query.filter(Client.expires_at <= datetime.utcnow())
    elif filter_type == "paused":
        query = query.filter(Client.status == "paused")

    all_clients = Client.query.all()
    counts = {
        "total": len(all_clients),
        "active": sum(1 for c in all_clients if c.is_active),
        "expired": sum(1 for c in all_clients if c.is_expired),
        "paused": sum(1 for c in all_clients if c.status == "paused"),
    }

    return render_template(
        "clients.html",
        clients=query.all(),
        filter=filter_type,
        counts=counts,
    )


@main_bp.route("/clients/add", methods=["GET", "POST"])
@login_required
def client_add():
    if request.method == "POST":
        months = int(request.form.get("months", 1))
        plan_id = request.form.get("plan_id", type=int)

        client = Client(
            nome=request.form["nome"],
            email=request.form["email"],
            teams_email=request.form["teams_email"],
            teams_password=request.form["teams_password"],
            anthropic_key=request.form["anthropic_key"],
            smtp_email=request.form.get("smtp_email", ""),
            smtp_password=request.form.get("smtp_password", ""),
            notification_email=request.form.get("notification_email", ""),
            whatsapp=request.form.get("whatsapp", ""),
            check_interval=int(request.form.get("check_interval", 60)),
            expires_at=datetime.utcnow() + timedelta(days=30 * months),
            status="active",
            plan_id=plan_id,
            mes_contagem=datetime.utcnow().month,
        )
        db.session.add(client)
        db.session.flush()

        # Registra pagamento
        amount = float(request.form.get("amount", 0))
        if amount > 0:
            payment = Payment(
                client_id=client.id,
                amount=amount,
                months=months,
            )
            db.session.add(payment)

        # Cria diretorio de dados
        client.data_dir  # property que cria o dir

        db.session.commit()

        # Agenda no scheduler
        try:
            from engine.scheduler import add_client_job
            add_client_job(client.id)
        except Exception:
            pass

        flash(f"Cliente {client.nome} cadastrado com sucesso!", "success")
        return redirect(url_for("main.client_detail", client_id=client.id))

    plans = Plan.query.filter_by(ativo=True).all()
    return render_template("client_form.html", client=None, plans=plans)


@main_bp.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    task_logs = TaskLog.query.filter_by(client_id=client_id).order_by(TaskLog.created_at.desc()).limit(50).all()
    payments = Payment.query.filter_by(client_id=client_id).order_by(Payment.created_at.desc()).all()

    return render_template(
        "client_detail.html",
        client=client,
        task_logs=task_logs,
        payments=payments,
    )


@main_bp.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def client_edit(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == "POST":
        client.nome = request.form["nome"]
        client.email = request.form["email"]
        client.teams_email = request.form["teams_email"]
        client.check_interval = int(request.form.get("check_interval", 60))
        client.smtp_email = request.form.get("smtp_email", "")
        client.notification_email = request.form.get("notification_email", "")
        client.whatsapp = request.form.get("whatsapp", "")
        client.plan_id = request.form.get("plan_id", type=int)

        # So atualiza senhas se preenchidas
        if request.form.get("teams_password"):
            client.teams_password = request.form["teams_password"]
        if request.form.get("anthropic_key"):
            client.anthropic_key = request.form["anthropic_key"]
        if request.form.get("smtp_password"):
            client.smtp_password = request.form["smtp_password"]

        db.session.commit()
        flash(f"Cliente {client.nome} atualizado!", "success")
        return redirect(url_for("main.client_detail", client_id=client.id))

    plans = Plan.query.filter_by(ativo=True).all()
    return render_template("client_form.html", client=client, plans=plans)


@main_bp.route("/clients/<int:client_id>/toggle", methods=["POST"])
@login_required
def client_toggle(client_id):
    client = Client.query.get_or_404(client_id)

    if client.status == "paused":
        client.status = "active"
        flash(f"{client.nome} ativado!", "success")
        try:
            from engine.scheduler import add_client_job
            add_client_job(client.id)
        except Exception:
            pass
    else:
        client.status = "paused"
        flash(f"{client.nome} pausado.", "warning")
        try:
            from engine.scheduler import remove_client_job
            remove_client_job(client.id)
        except Exception:
            pass

    db.session.commit()
    return redirect(request.referrer or url_for("main.clients"))


@main_bp.route("/clients/<int:client_id>/renew", methods=["POST"])
@login_required
def client_renew(client_id):
    client = Client.query.get_or_404(client_id)
    months = int(request.form.get("months", 1))
    amount = float(request.form.get("amount", 0))

    client.renew(months)

    payment = Payment(client_id=client.id, amount=amount, months=months)
    db.session.add(payment)
    db.session.commit()

    # Re-agenda no scheduler
    try:
        from engine.scheduler import add_client_job
        add_client_job(client.id)
    except Exception:
        pass

    flash(f"{client.nome} renovado por {months} mes(es)!", "success")
    return redirect(url_for("main.client_detail", client_id=client.id))


@main_bp.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def client_delete(client_id):
    client = Client.query.get_or_404(client_id)
    nome = client.nome

    try:
        from engine.scheduler import remove_client_job
        remove_client_job(client.id)
    except Exception:
        pass

    # Remove logs e pagamentos
    TaskLog.query.filter_by(client_id=client_id).delete()
    Payment.query.filter_by(client_id=client_id).delete()
    db.session.delete(client)
    db.session.commit()

    flash(f"Cliente {nome} excluido.", "danger")
    return redirect(url_for("main.clients"))


@main_bp.route("/clients/<int:client_id>/run", methods=["POST"])
@login_required
def client_run_now(client_id):
    client = Client.query.get_or_404(client_id)

    try:
        from engine.scheduler import run_client_now
        run_client_now(client.id)
        flash(f"Execucao iniciada para {client.nome}!", "info")
    except Exception as e:
        flash(f"Erro ao iniciar execucao: {e}", "danger")

    return redirect(url_for("main.client_detail", client_id=client.id))


@main_bp.route("/clients/run-all", methods=["POST"])
@login_required
def clients_run_all():
    """Executa todos os clientes ativos agora."""
    from datetime import datetime

    active_clients = Client.query.filter(
        Client.status == "active",
        Client.expires_at > datetime.utcnow()
    ).all()

    if not active_clients:
        flash("Nenhum cliente ativo encontrado.", "warning")
        return redirect(url_for("main.clients"))

    count = 0
    errors = []

    try:
        from engine.scheduler import run_client_now
        for client in active_clients:
            try:
                run_client_now(client.id)
                count += 1
            except Exception as e:
                errors.append(f"{client.nome}: {e}")
    except Exception as e:
        flash(f"Erro ao iniciar execucoes: {e}", "danger")
        return redirect(url_for("main.clients"))

    if count > 0:
        flash(f"Execucao iniciada para {count} cliente(s)!", "success")
    if errors:
        flash(f"Erros: {', '.join(errors[:3])}", "warning")

    return redirect(url_for("main.clients"))


@main_bp.route("/logs")
@login_required
def logs():
    page = int(request.args.get("page", 1))
    per_page = 50
    selected_client = request.args.get("client_id", "", type=int) or None
    selected_status = request.args.get("status", "")
    search_query = request.args.get("q", "").strip()
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = TaskLog.query.order_by(TaskLog.created_at.desc())

    if selected_client:
        query = query.filter_by(client_id=selected_client)
    if selected_status:
        query = query.filter_by(status=selected_status)
    if search_query:
        query = query.filter(TaskLog.task_name.ilike(f"%{search_query}%"))
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(TaskLog.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(TaskLog.created_at < dt_to)
        except ValueError:
            pass

    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    logs_list = query.offset((page - 1) * per_page).limit(per_page).all()

    all_clients = Client.query.order_by(Client.nome).all()

    return render_template(
        "logs.html",
        logs=logs_list,
        all_clients=all_clients,
        selected_client=selected_client,
        selected_status=selected_status,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@main_bp.route("/logs/export")
@login_required
def logs_export():
    """Exporta logs em CSV."""
    import csv
    import io
    from flask import Response

    selected_client = request.args.get("client_id", "", type=int) or None
    selected_status = request.args.get("status", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = TaskLog.query.order_by(TaskLog.created_at.desc())

    if selected_client:
        query = query.filter_by(client_id=selected_client)
    if selected_status:
        query = query.filter_by(status=selected_status)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(TaskLog.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(TaskLog.created_at < dt_to)
        except ValueError:
            pass

    logs_list = query.limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data", "Cliente", "Tarefa", "Disciplina", "Formato", "Status", "Erro"])

    for log in logs_list:
        writer.writerow([
            log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            log.client.nome,
            log.task_name,
            log.discipline or "",
            log.format or "",
            log.status,
            log.error_msg or ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )


# ============================================
# WEBHOOK PARA AUTO-DEPLOY
# ============================================

@main_bp.route("/webhook/deploy", methods=["POST"])
def webhook_deploy():
    """Webhook do GitHub para auto-deploy."""
    import hashlib
    import hmac
    import subprocess
    import os
    from loguru import logger

    # Segredo para validar webhook (configure no .env e no GitHub)
    webhook_secret = os.getenv("WEBHOOK_SECRET", "")

    if webhook_secret:
        # Valida assinatura do GitHub
        signature = request.headers.get("X-Hub-Signature-256", "")
        if signature:
            expected = "sha256=" + hmac.new(
                webhook_secret.encode(),
                request.data,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected):
                logger.warning("Webhook: assinatura invalida!")
                return {"error": "Invalid signature"}, 403

    # Verifica se é push na branch main
    data = request.json or {}
    ref = data.get("ref", "")
    if ref != "refs/heads/main":
        return {"status": "ignored", "reason": "not main branch"}, 200

    logger.info("Webhook: iniciando deploy...")

    try:
        # Executa deploy em background
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        deploy_script = f"""
cd {project_dir}
git pull origin main
pkill -f "python app.py" || true
sleep 2
source venv/bin/activate
nohup python app.py > logs/server.log 2>&1 &
"""
        subprocess.Popen(["bash", "-c", deploy_script], start_new_session=True)
        logger.info("Webhook: deploy iniciado com sucesso!")
        return {"status": "deploying"}, 200

    except Exception as e:
        logger.error(f"Webhook: erro no deploy: {e}")
        return {"error": str(e)}, 500
