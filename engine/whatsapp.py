"""
Integração com UazAPI para notificações WhatsApp.
Documentação: https://uazapi.com/docs
"""

import os
import requests
from loguru import logger

UAZAPI_URL = os.getenv("UAZAPI_URL", "")  # URL da instância
UAZAPI_TOKEN = os.getenv("UAZAPI_TOKEN", "")  # Token de autenticação


def enviar_whatsapp(numero: str, mensagem: str) -> bool:
    """
    Envia mensagem WhatsApp via UazAPI.

    Args:
        numero: Número com DDD (ex: 11999998888)
        mensagem: Texto da mensagem

    Returns:
        True se enviou com sucesso
    """
    if not UAZAPI_URL or not UAZAPI_TOKEN:
        logger.warning("UazAPI não configurada (UAZAPI_URL e UAZAPI_TOKEN)")
        return False

    # Formata número para padrão internacional
    numero_limpo = "".join(filter(str.isdigit, numero))
    if not numero_limpo.startswith("55"):
        numero_limpo = f"55{numero_limpo}"

    try:
        response = requests.post(
            f"{UAZAPI_URL}/message/send-text",
            headers={
                "Authorization": f"Bearer {UAZAPI_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "phone": numero_limpo,
                "message": mensagem
            },
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f"WhatsApp enviado para {numero_limpo}")
            return True
        else:
            logger.error(f"Erro ao enviar WhatsApp: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Erro ao enviar WhatsApp: {e}")
        return False


def notificar_tarefa_enviada(numero: str, nome_cliente: str, nome_tarefa: str, disciplina: str):
    """Notifica que uma tarefa foi enviada com sucesso."""
    mensagem = f"""✅ *Tarefa Enviada!*

👤 *Cliente:* {nome_cliente}
📚 *Disciplina:* {disciplina}
📝 *Tarefa:* {nome_tarefa}

_Teams Auto Solver_"""

    return enviar_whatsapp(numero, mensagem)


def notificar_erro(numero: str, nome_cliente: str, erro: str):
    """Notifica que houve um erro."""
    mensagem = f"""❌ *Erro no Teams Solver*

👤 *Cliente:* {nome_cliente}
⚠️ *Erro:* {erro}

Verifique o painel para mais detalhes.

_Teams Auto Solver_"""

    return enviar_whatsapp(numero, mensagem)


def notificar_ciclo_concluido(numero: str, nome_cliente: str, tarefas_enviadas: int, erros: int):
    """Notifica resumo do ciclo."""
    if tarefas_enviadas == 0 and erros == 0:
        return False  # Não notifica se não teve nada

    status = "✅" if erros == 0 else "⚠️"

    mensagem = f"""{status} *Ciclo Concluído*

👤 *Cliente:* {nome_cliente}
📊 *Resultado:*
   • Tarefas enviadas: {tarefas_enviadas}
   • Erros: {erros}

_Teams Auto Solver_"""

    return enviar_whatsapp(numero, mensagem)


def notificar_assinatura_vencendo(numero: str, nome_cliente: str, dias_restantes: int):
    """Notifica que a assinatura está vencendo."""
    mensagem = f"""⏰ *Assinatura Vencendo!*

👤 *Cliente:* {nome_cliente}
📅 *Dias restantes:* {dias_restantes}

Renove para continuar usando o serviço.

_Teams Auto Solver_"""

    return enviar_whatsapp(numero, mensagem)


def notificar_admin_erro(numero_admin: str, nome_cliente: str, erro: str, client_id: int):
    """Notifica o admin sobre erro de um cliente."""
    mensagem = f"""🚨 *Alerta Admin*

👤 *Cliente:* {nome_cliente} (ID: {client_id})
❌ *Erro:* {erro}

Acesse o painel para verificar.

_Teams Auto Solver_"""

    return enviar_whatsapp(numero_admin, mensagem)
