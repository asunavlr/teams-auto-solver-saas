"""Autenticacao admin do painel."""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import UserMixin, login_user, logout_user, login_required
from web import login_manager
import config as cfg

auth_bp = Blueprint("auth", __name__)


class AdminUser(UserMixin):
    def __init__(self):
        self.id = "admin"


@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return AdminUser()
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == cfg.ADMIN_USERNAME and password == cfg.ADMIN_PASSWORD:
            login_user(AdminUser())
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))

        flash("Usuario ou senha incorretos.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
