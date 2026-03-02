"""
Funcao para reenviar tarefas com novos arquivos no Teams.
"""

import asyncio
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger

from engine.browser import TeamsBrowser
from engine.agent import TeamsAgent


def log(msg: str, client_name: str = ""):
    prefix = f"[{client_name}] " if client_name else ""
    logger.info(f"{prefix}[RESUBMIT] {msg}")


async def reenviar_tarefa(
    client_id: int,
    task_name: str,
    discipline: str,
    arquivos: list,
    teams_email: str,
    teams_password: str,
    data_dir: Path,
    auth_state_path: Path,
    client_name: str = "",
) -> dict:
    """
    Desfaz o envio de uma tarefa e reenvia com novos arquivos.

    Args:
        client_id: ID do cliente
        task_name: Nome da tarefa
        discipline: Disciplina da tarefa
        arquivos: Lista de caminhos dos arquivos para enviar
        teams_email: Email do Teams
        teams_password: Senha do Teams
        data_dir: Diretorio de dados do cliente
        auth_state_path: Caminho do arquivo de estado de autenticacao
        client_name: Nome do cliente para logs

    Returns:
        Dict com status e mensagem
    """
    resultado = {"success": False, "message": ""}

    log(f"Iniciando reenvio: {task_name[:50]} com {len(arquivos)} arquivo(s)", client_name)

    browser = TeamsBrowser(
        auth_state_path=auth_state_path,
        teams_email=teams_email,
        teams_password=teams_password,
    )

    headless = os.environ.get("HEADLESS", "true").lower() != "false"
    await browser.start(headless=headless)

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

        if not tarefa_encontrada:
            resultado["message"] = f"Tarefa nao encontrada: {task_name[:50]}"
            return resultado

        await asyncio.sleep(4)

        # Atualiza frame
        for f in browser.page.frames:
            if "assignments" in f.url.lower():
                frame = f
                break

        # PASSO 1: Desfazer entrega
        log("Desfazendo entrega atual...", client_name)
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
            log("Confirmacao de undo clicada", client_name)
        except Exception:
            pass

        await asyncio.sleep(3)

        # Atualiza frame novamente
        for f in browser.page.frames:
            if "assignments" in f.url.lower():
                frame = f
                break

        # PASSO 2: Remover arquivos anteriores (via menu ... > Excluir)
        log("Removendo arquivos anteriores...", client_name)

        remove_attempts = 0
        max_remove_attempts = 10  # Maximo de arquivos para remover

        while remove_attempts < max_remove_attempts:
            removed = False

            # Procura o botao de menu "..." (More options) do arquivo
            menu_selectors = [
                'button:has-text("...")',
                'button:has-text("⋯")',
                'button:has-text("•••")',
                'button[aria-label*="More options"]',
                'button[aria-label*="More actions"]',
                'button[aria-label*="Mais opções"]',
                'button[aria-label*="Mais opcoes"]',
                'button[aria-label*="Mais ações"]',
                'button[aria-label*="actions"]',
                '[data-tid="file-more-options"]',
                '[data-tid="more-options"]',
                '.my-work-item button[aria-haspopup="menu"]',
                '.attachment-card button[aria-haspopup="menu"]',
            ]

            menu_clicked = False

            # Tenta clicar no menu "..." no frame
            for selector in menu_selectors:
                try:
                    menu_btn = frame.locator(selector).first
                    if await menu_btn.is_visible(timeout=1000):
                        await menu_btn.click(timeout=2000)
                        menu_clicked = True
                        log(f"Menu ... clicado: {selector}", client_name)
                        await asyncio.sleep(1)
                        break
                except Exception:
                    continue

            # Tenta na pagina principal
            if not menu_clicked:
                for selector in menu_selectors:
                    try:
                        menu_btn = browser.page.locator(selector).first
                        if await menu_btn.is_visible(timeout=1000):
                            await menu_btn.click(timeout=2000)
                            menu_clicked = True
                            log(f"Menu ... clicado (pagina): {selector}", client_name)
                            await asyncio.sleep(1)
                            break
                    except Exception:
                        continue

            if not menu_clicked:
                log("Nenhum menu ... encontrado, assumindo sem arquivos anteriores", client_name)
                break

            # Agora clica em "Excluir" / "Delete" no menu
            delete_selectors = [
                'button:has-text("Delete")',
                'button:has-text("Excluir")',
                'menuitem:has-text("Delete")',
                'menuitem:has-text("Excluir")',
                '[role="menuitem"]:has-text("Delete")',
                '[role="menuitem"]:has-text("Excluir")',
            ]

            for selector in delete_selectors:
                try:
                    delete_btn = frame.locator(selector).first
                    if await delete_btn.is_visible(timeout=2000):
                        await delete_btn.click(timeout=2000)
                        removed = True
                        log(f"Excluir clicado: {selector}", client_name)
                        await asyncio.sleep(1)
                        break
                except Exception:
                    continue

            # Tenta na pagina principal
            if not removed:
                for selector in delete_selectors:
                    try:
                        delete_btn = browser.page.locator(selector).first
                        if await delete_btn.is_visible(timeout=2000):
                            await delete_btn.click(timeout=2000)
                            removed = True
                            log(f"Excluir clicado (pagina): {selector}", client_name)
                            await asyncio.sleep(1)
                            break
                    except Exception:
                        continue

            if not removed:
                log("Menu aberto mas opcao Excluir nao encontrada", client_name)
                # Fecha o menu clicando fora
                try:
                    await browser.page.keyboard.press("Escape")
                except Exception:
                    pass
                break

            remove_attempts += 1
            await asyncio.sleep(1)

        if remove_attempts > 0:
            log(f"{remove_attempts} arquivo(s) anterior(es) removido(s)", client_name)

        await asyncio.sleep(2)

        # PASSO 3: Adicionar novos arquivos
        log(f"Adicionando {len(arquivos)} novo(s) arquivo(s)...", client_name)

        # Procura botao de adicionar arquivo
        add_file_selectors = [
            'button:has-text("Add work")',
            'button:has-text("Adicionar trabalho")',
            'button:has-text("Add new")',
            'button:has-text("Adicionar novo")',
            'button:has-text("Attach")',
            'button:has-text("Anexar")',
            '[data-tid="add-work-button"]',
            'input[type="file"]',
        ]

        file_input = None

        # Tenta encontrar input file direto
        try:
            file_input = frame.locator('input[type="file"]').first
            if not await file_input.is_visible():
                file_input = None
        except Exception:
            pass

        if not file_input:
            try:
                file_input = browser.page.locator('input[type="file"]').first
                if not await file_input.is_visible():
                    file_input = None
            except Exception:
                pass

        # Se nao achou input, clica no botao para revelar
        if not file_input:
            for selector in add_file_selectors:
                if 'input[type="file"]' in selector:
                    continue
                try:
                    add_btn = frame.locator(selector).first
                    await add_btn.click(timeout=3000)
                    log(f"Botao Add work clicado: {selector}", client_name)
                    await asyncio.sleep(2)
                    break
                except Exception:
                    continue

            # Tenta encontrar "Upload from this device"
            try:
                upload_device = frame.locator(
                    'button:has-text("Upload from this device"), '
                    'button:has-text("Carregar deste dispositivo"), '
                    'button:has-text("From device")'
                ).first
                await upload_device.click(timeout=3000)
                log("Upload from device clicado", client_name)
                await asyncio.sleep(2)
            except Exception:
                pass

            # Agora procura o input file
            try:
                file_input = frame.locator('input[type="file"]').first
            except Exception:
                pass

            if not file_input:
                try:
                    file_input = browser.page.locator('input[type="file"]').first
                except Exception:
                    pass

        if not file_input:
            resultado["message"] = "Nao encontrou campo de upload de arquivo"
            return resultado

        # Faz upload dos arquivos
        try:
            await file_input.set_input_files(arquivos)
            log(f"Arquivos enviados para upload: {[os.path.basename(a) for a in arquivos]}", client_name)
        except Exception as e:
            log(f"Erro no upload: {e}", client_name)
            resultado["message"] = f"Erro ao fazer upload: {str(e)}"
            return resultado

        await asyncio.sleep(5)  # Aguarda upload completar

        # PASSO 4: Enviar/Entregar
        log("Enviando tarefa...", client_name)

        submit_selectors = [
            'button:has-text("Turn in again")',
            'button:has-text("Entregar novamente")',
            'button:has-text("Turn in")',
            'button:has-text("Entregar")',
            'button:has-text("Submit")',
            'button:has-text("Enviar")',
            '[data-tid="turn-in-button"]',
        ]

        submitted = False

        for selector in submit_selectors:
            try:
                submit_btn = frame.locator(selector).first
                await submit_btn.click(timeout=5000)
                submitted = True
                log(f"Botao Submit clicado: {selector}", client_name)
                break
            except Exception:
                continue

        if not submitted:
            for selector in submit_selectors:
                try:
                    submit_btn = browser.page.locator(selector).first
                    await submit_btn.click(timeout=5000)
                    submitted = True
                    log(f"Botao Submit clicado (pagina): {selector}", client_name)
                    break
                except Exception:
                    continue

        if not submitted:
            resultado["message"] = "Nao encontrou botao de enviar"
            return resultado

        await asyncio.sleep(3)

        # Confirma se tiver dialog
        try:
            confirm_btn = browser.page.locator(
                'button:has-text("Turn in again"), button:has-text("Entregar novamente"), '
                'button:has-text("Turn in"), button:has-text("Entregar"), '
                'button:has-text("Done"), button:has-text("Concluir")'
            ).first
            await confirm_btn.click(timeout=3000)
            log("Confirmacao de envio clicada", client_name)
        except Exception:
            pass

        await asyncio.sleep(3)

        # Tira screenshot de comprovacao
        screenshot_path = data_dir / f"resubmit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await browser.page.screenshot(path=str(screenshot_path))
        log(f"Screenshot salvo: {screenshot_path}", client_name)

        # Move arquivos para pasta do cliente (backup)
        backup_dir = data_dir / "resubmit_files"
        backup_dir.mkdir(parents=True, exist_ok=True)

        for arquivo in arquivos:
            try:
                arquivo_path = Path(arquivo)
                if arquivo_path.exists():
                    dest = backup_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{arquivo_path.name}"
                    shutil.copy2(arquivo, dest)
                    log(f"Arquivo copiado para backup: {dest.name}", client_name)
            except Exception as e:
                log(f"Erro ao copiar arquivo para backup: {e}", client_name)

        resultado["success"] = True
        resultado["message"] = "Tarefa reenviada com sucesso"
        log("Tarefa reenviada com sucesso!", client_name)

    except Exception as e:
        log(f"Erro ao reenviar tarefa: {e}", client_name)
        resultado["message"] = str(e)

    finally:
        await browser.close()

        # Limpa arquivos temporarios de upload
        for arquivo in arquivos:
            try:
                arquivo_path = Path(arquivo)
                if arquivo_path.exists():
                    arquivo_path.unlink()
                # Tenta remover pasta pai se vazia
                parent = arquivo_path.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except Exception:
                pass

    return resultado
