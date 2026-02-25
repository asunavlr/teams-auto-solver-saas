"""Notificacoes por email - por cliente."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger


class EmailNotifier:
    def __init__(self, smtp_email: str, smtp_password: str, to_email: str,
                 smtp_server: str = "smtp.gmail.com", smtp_port: int = 587):
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.to_email = to_email
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def send(self, subject: str, body: str):
        if not self.smtp_email or not self.smtp_password or not self.to_email:
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_email
            msg["To"] = self.to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_email, self.smtp_password)
                server.sendmail(self.smtp_email, self.to_email, msg.as_string())

            logger.info(f"Email enviado para {self.to_email}")
        except Exception as e:
            logger.error(f"Erro ao enviar email: {e}")

    def notify_tarefa_resolvida(self, nome_tarefa: str, disciplina: str, resposta: str):
        subject = f"Tarefa Resolvida: {nome_tarefa}"
        body = f"""
        <h2>Tarefa Resolvida Automaticamente</h2>
        <p><strong>Tarefa:</strong> {nome_tarefa}</p>
        <p><strong>Disciplina:</strong> {disciplina}</p>
        <p><strong>Resposta (preview):</strong></p>
        <pre>{resposta[:500]}...</pre>
        <hr>
        <small>Teams Auto Solver</small>
        """
        self.send(subject, body)
