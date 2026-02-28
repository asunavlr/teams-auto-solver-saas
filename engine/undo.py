"""
Funcao para desfazer envio de tarefas no Teams.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from engine.browser import TeamsBrowser
from engine.agent import TeamsAgent


def log(msg: str, client_name: str = ""):
    prefix = f"[{client_name}] " if client_name else ""
    logger.info(f"{prefix}[UNDO] {msg}")


async def desfazer_envio(
    client_id: int,
    task_name: str,
    discipline: str,
    reprocessar: bool,
    teams_email: str,
    teams_password: str,
    anthropic_key: str,
    data_dir: Path,
    auth_state_path: Path,
    client_name: str = "",
) -> dict:
    """
    Desfaz o envio de uma tarefa no Teams.

    Args:
        client_id: ID do cliente
        task_name: Nome da tarefa
        discipline: Disciplina da tarefa
        reprocessar: Se True, remove do processadas.json para reprocessar
        teams_email: Email do Teams
        teams_password: Senha do Teams
        anthropic_key: Chave da API Anthropic
        data_dir: Diretorio de dados do cliente
        auth_state_path: Caminho do arquivo de estado de autenticacao
        client_name: Nome do cliente para logs

    Returns:
        Dict com status e mensagem
    """
    resultado = {"success": False, "message": "", "reprocessar": reprocessar}

    log(f"Iniciando desfazer envio: {task_name[:50]}", client_name)

    browser = TeamsBrowser(
        auth_state_path=auth_state_path,
        teams_email=teams_email,
        teams_password=teams_password,
    )

    import os
    headless = os.environ.get("HEADLESS", "true").lower() != "false"
    await browser.start(headless=headless)

    agent = TeamsAgent(browser.page, anthropic_key)

    try:
        # Conecta ao Teams
        log("Conectando ao Teams...", client_name)
        await browser.page.goto("https://teams.microsoft.com")

        try:
            await browser.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(5)

        # Verifica se precisa fazer login
        page_content = await browser.page.inner_text("body")
        if "Sign in" in page_content or "Entrar" in page_content:
            log("Sessao expirada, fazendo login...", client_name)
            login_ok = await browser.login()
            if not login_ok:
                resultado["message"] = "Falha no login do Teams"
                return resultado
            await asyncio.sleep(5)

        # Navega para Assignments
        log("Navegando para Assignments...", client_name)
        try:
            assignments_btn = browser.page.locator(
                'button:has-text("Assignments"), button:has-text("Atribuicoes"), button:has-text("Atribuições")'
            ).first
            await assignments_btn.click(timeout=10000)
        except Exception:
            # Tenta via Vision
            clicked = await agent.clicar("tarefas")
            if not clicked:
                resultado["message"] = "Nao conseguiu acessar Assignments"
                return resultado

        await asyncio.sleep(4)

        # Busca frame de assignments
        frame = None
        for f in browser.page.frames:
            if "assignments" in f.url.lower():
                frame = f
                break

        if not frame:
            frame = browser.page

        # Clica na aba Completed/Concluido
        log("Acessando aba Completed...", client_name)
        completed_clicked = False

        for tab_name in ["Completed", "Concluído", "Concluido", "Done"]:
            try:
                tab_btn = frame.locator(f'text="{tab_name}"').first
                await tab_btn.click(timeout=3000)
                completed_clicked = True
                log(f"Aba '{tab_name}' clicada", client_name)
                break
            except Exception:
                continue

        if not completed_clicked:
            # Tenta Vision
            log("Tentando Vision para aba Completed...", client_name)
            completed_clicked = await agent._clicar_com_visao(
                "Aba 'Completed' ou 'Concluido' na lista de tarefas"
            )

        if not completed_clicked:
            resultado["message"] = "Nao encontrou aba Completed"
            return resultado

        await asyncio.sleep(3)

        # Busca a tarefa pelo nome
        log(f"Buscando tarefa: {task_name[:40]}...", client_name)
        tarefa_encontrada = False

        # Limpa nome para regex
        nome_limpo = re.sub(r'[()\\/*+?\[\]{}|^$.]', '', task_name).strip()

        # Tenta CSS primeiro
        try:
            task_element = frame.locator(f'text=/{re.escape(nome_limpo[:40])}/i').first
            await task_element.click(timeout=5000)
            tarefa_encontrada = True
            log("Tarefa encontrada via CSS", client_name)
        except Exception:
            pass

        # Fallback: Vision
        if not tarefa_encontrada:
            log("Tentando Vision para encontrar tarefa...", client_name)
            nome_curto = " ".join(task_name.split()[:5])
            tarefa_encontrada = await agent._clicar_com_visao(
                f"Tarefa com nome '{nome_curto}' na lista de tarefas concluidas"
            )

        if not tarefa_encontrada:
            resultado["message"] = f"Tarefa nao encontrada: {task_name[:50]}"
            return resultado

        await asyncio.sleep(4)

        # Atualiza frame
        for f in browser.page.frames:
            if "assignments" in f.url.lower():
                frame = f
                break

        # Clica em "Undo turn in" / "Desfazer entrega"
        log("Procurando botao Undo turn in...", client_name)
        undo_clicked = False

        undo_selectors = [
            'button:has-text("Undo turn in")',
            'button:has-text("Desfazer entrega")',
            'button:has-text("Undo submission")',
            '[data-tid="undo-turn-in"]',
        ]

        for selector in undo_selectors:
            try:
                undo_btn = frame.locator(selector).first
                await undo_btn.click(timeout=3000)
                undo_clicked = True
                log(f"Botao Undo clicado: {selector}", client_name)
                break
            except Exception:
                continue

        # Tenta na pagina principal
        if not undo_clicked:
            for selector in undo_selectors:
                try:
                    undo_btn = browser.page.locator(selector).first
                    await undo_btn.click(timeout=3000)
                    undo_clicked = True
                    log(f"Botao Undo clicado (pagina): {selector}", client_name)
                    break
                except Exception:
                    continue

        # Fallback: Vision
        if not undo_clicked:
            log("Tentando Vision para botao Undo...", client_name)
            undo_clicked = await agent._clicar_com_visao(
                "Botao 'Undo turn in' ou 'Desfazer entrega' para cancelar o envio da tarefa"
            )

        if not undo_clicked:
            resultado["message"] = "Nao encontrou botao Undo turn in"
            return resultado

        await asyncio.sleep(2)

        # Confirma se tiver dialog
        try:
            confirm_btn = browser.page.locator(
                'button:has-text("Undo"), button:has-text("Desfazer"), button:has-text("Yes"), button:has-text("Sim")'
            ).first
            await confirm_btn.click(timeout=3000)
            log("Confirmacao clicada", client_name)
        except Exception:
            pass

        await asyncio.sleep(3)

        # Tira screenshot de comprovacao
        screenshot_path = data_dir / f"undo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await browser.page.screenshot(path=str(screenshot_path))
        log(f"Screenshot salvo: {screenshot_path}", client_name)

        # Se reprocessar, remove do processadas.json
        if reprocessar:
            processadas_path = data_dir / "processadas.json"
            if processadas_path.exists():
                try:
                    with open(processadas_path, "r") as f:
                        processadas = json.load(f)

                    # Busca o ID da tarefa pelo nome
                    task_id_to_remove = None
                    for task_id, task_info in processadas.items():
                        if isinstance(task_info, dict):
                            if task_info.get("nome", "") == task_name:
                                task_id_to_remove = task_id
                                break
                        elif task_info == task_name:
                            task_id_to_remove = task_id
                            break

                    if task_id_to_remove:
                        del processadas[task_id_to_remove]
                        with open(processadas_path, "w") as f:
                            json.dump(processadas, f, ensure_ascii=False, indent=2)
                        log(f"Tarefa removida de processadas.json: {task_id_to_remove}", client_name)
                    else:
                        log("Tarefa nao encontrada em processadas.json", client_name)

                except Exception as e:
                    log(f"Erro ao atualizar processadas.json: {e}", client_name)

        resultado["success"] = True
        resultado["message"] = "Envio desfeito com sucesso"
        log("Envio desfeito com sucesso!", client_name)

    except Exception as e:
        log(f"Erro ao desfazer envio: {e}", client_name)
        resultado["message"] = str(e)

    finally:
        await browser.close()

    return resultado
