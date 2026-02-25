"""
Ciclo de monitoramento por cliente.
Refatorado de monitorar_activity.py para suportar multi-tenant.
"""

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from docx import Document
from loguru import logger

from engine.browser import TeamsBrowser
from engine.solver import (
    resolver_com_claude,
    detectar_formato_resposta,
    detectar_formato_da_resposta,
    remover_marcador_formato,
    criar_arquivo_resposta,
    extrair_multiplos_arquivos,
    extrair_projeto_multi_arquivo,
    FORMATOS_CODIGO,
)
from engine.notifier import EmailNotifier

MAX_PDF_PAGES = 15


class ClientConfig:
    """Configuracao de um cliente para monitoramento."""

    def __init__(self, client_id: int, nome: str, teams_email: str,
                 teams_password: str, anthropic_key: str,
                 data_dir: Path, check_interval: int = 60,
                 smtp_email: str = "", smtp_password: str = "",
                 notification_email: str = ""):
        self.client_id = client_id
        self.nome = nome
        self.teams_email = teams_email
        self.teams_password = teams_password
        self.anthropic_key = anthropic_key
        self.data_dir = Path(data_dir)
        self.check_interval = check_interval
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.notification_email = notification_email

        # Garante que o diretorio existe
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def auth_state_path(self) -> Path:
        return self.data_dir / "auth_state.json"

    @property
    def processadas_path(self) -> Path:
        return self.data_dir / "processadas.json"


def log(msg: str, client_name: str = ""):
    prefix = f"[{client_name}] " if client_name else ""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"{prefix}{msg}")


def carregar_processadas(path: Path) -> set:
    if path.exists():
        with open(path, "r") as f:
            return set(json.load(f))
    return set()


def salvar_processadas(processadas: set, path: Path):
    with open(path, "w") as f:
        json.dump(list(processadas), f)


async def verificar_activity(browser, data_dir: Path, client_name: str = "", max_tentativas: int = 3) -> list:
    """Verifica a aba Activity e retorna novas atividades.

    Se não encontrar atividades, tenta novamente até max_tentativas vezes,
    esperando 10 segundos entre cada tentativa.
    """
    log("Acessando Activity...", client_name)

    try:
        activity_btn = browser.page.locator('button:has-text("Activity")').first
        await activity_btn.click(timeout=5000)
    except Exception:
        try:
            activity_btn = browser.page.locator('button:has-text("Atividade")').first
            await activity_btn.click(timeout=5000)
        except Exception:
            activity_btn = browser.page.locator('[aria-label*="Activity"], [aria-label*="Atividade"]').first
            await activity_btn.click(timeout=5000)

    for tentativa in range(1, max_tentativas + 1):
        # Espera inicial maior na primeira tentativa, 10s nas seguintes
        tempo_espera = 6 if tentativa == 1 else 10
        await asyncio.sleep(tempo_espera)

        await browser.page.screenshot(path=str(data_dir / "activity_atual.png"))
        content = await browser.page.inner_text("body")

        with open(data_dir / "activity_content.txt", "w", encoding="utf-8") as f:
            f.write(content)

        atividades = []
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if "adicionou uma tarefa" in line or "atualizou uma tarefa" in line:
                atividade = {
                    "tipo": "assignment",
                    "professor": line.split(" adicion")[0].split(" atualiz")[0].strip(),
                    "acao": "nova" if "adicionou" in line else "atualizada"
                }

                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    if "Conclus" in next_line:
                        atividade["prazo"] = next_line
                    elif "|" in next_line:
                        parts = next_line.split("|")
                        atividade["disciplina"] = parts[0].strip()
                        atividade["nome"] = parts[1].strip() if len(parts) > 1 else ""
                    elif re.match(r"^\d{1,2}/\d{1,2}$", next_line):
                        atividade["data"] = next_line

                if atividade.get("nome"):
                    atividade["id"] = hashlib.md5(
                        (atividade["nome"] + atividade.get("disciplina", "")).encode()
                    ).hexdigest()
                    atividades.append(atividade)
                    log(f"  Encontrada: {atividade['nome']}", client_name)

                i += 4
            else:
                i += 1

        # Se encontrou atividades, retorna
        if atividades:
            log(f"Total: {len(atividades)} atividades encontradas", client_name)
            return atividades

        # Se não encontrou e ainda tem tentativas, tenta de novo
        if tentativa < max_tentativas:
            log(f"Nenhuma atividade encontrada, tentativa {tentativa}/{max_tentativas}. Aguardando 10s...", client_name)
        else:
            log(f"Total: 0 atividades encontradas (apos {max_tentativas} tentativas)", client_name)

    return []


async def buscar_tarefa_no_frame(frame, nome_tarefa: str) -> bool:
    """Busca e clica na tarefa pelo nome."""
    nome_limpo = re.sub(r'[()\\/*+?\[\]{}|^$.]', '', nome_tarefa).strip()

    try:
        task = frame.locator(f'text=/{re.escape(nome_limpo)}/i').first
        await task.click(timeout=5000)
        return True
    except Exception:
        pass

    for tamanho in [40, 30, 20]:
        if len(nome_limpo) <= tamanho:
            continue
        try:
            trecho = nome_limpo[:tamanho].strip()
            resultados = frame.locator(f'text=/{re.escape(trecho)}/i')
            count = await resultados.count()

            if count == 1:
                await resultados.first.click(timeout=5000)
                return True
            elif count > 1:
                for idx in range(count):
                    texto = await resultados.nth(idx).inner_text()
                    if nome_tarefa.lower() in texto.lower() or texto.lower() in nome_tarefa.lower():
                        await resultados.nth(idx).click(timeout=5000)
                        return True
                await resultados.first.click(timeout=5000)
                return True
        except Exception:
            continue

    return False


async def fechar_preview(browser):
    """Fecha qualquer preview aberto."""
    await asyncio.sleep(2)

    close_selectors = [
        'button:has-text("Close")', 'button:has-text("Fechar")',
        'button[aria-label="Close"]', 'button[aria-label="Fechar"]',
        'button[aria-label*="Close"]', '[data-testid="close-button"]',
        '.ms-Dialog-button--close', 'button.closeButton',
        'i[data-icon-name="Cancel"]', 'button:has(i[data-icon-name="Cancel"])',
        '[aria-label="Close preview"]', 'button[title="Close"]', 'button[title="Fechar"]',
    ]

    fechado = False
    for selector in close_selectors:
        if fechado:
            break
        try:
            btn = browser.page.locator(selector).first
            await btn.click(timeout=2000)
            fechado = True
        except Exception:
            pass

    if not fechado:
        for f in browser.page.frames:
            if fechado:
                break
            for selector in close_selectors[:5]:
                try:
                    btn = f.locator(selector).first
                    await btn.click(timeout=1500)
                    fechado = True
                    break
                except Exception:
                    pass

    if not fechado:
        for _ in range(3):
            await browser.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

    try:
        await browser.page.mouse.click(5, 5)
        await asyncio.sleep(0.5)
    except Exception:
        pass

    await asyncio.sleep(1)


async def recuperar_frame_tarefa(browser, frame, nome_tarefa):
    """Recupera o frame de assignments se perdido."""
    for f in browser.page.frames:
        if "assignments" in f.url.lower():
            return f

    log("  Frame perdido, navegando de volta...")
    assignments_btn = browser.page.locator(
        'button:has-text("Assignments"), button:has-text("Atribuicoes"), button:has-text("Atribuições")'
    ).first
    await assignments_btn.click(timeout=10000)
    await asyncio.sleep(4)

    frame = None
    for f in browser.page.frames:
        if "assignments" in f.url.lower():
            frame = f
            break

    if frame:
        for tab in ["Em breve", "Em atraso", "Upcoming", "Past due"]:
            try:
                tab_btn = frame.locator(f'text="{tab}"').first
                await tab_btn.click(timeout=5000)
                await asyncio.sleep(2)
                if await buscar_tarefa_no_frame(frame, nome_tarefa):
                    await asyncio.sleep(4)
                    break
            except Exception:
                continue

    return frame


async def processar_nova_atividade(browser, atividade: dict, config: ClientConfig) -> str | bool:
    """Processa uma nova atividade para um cliente."""
    nome_tarefa = atividade.get("nome", "")
    disciplina = atividade.get("disciplina", "")
    data_dir = config.data_dir

    log(f"Processando: {nome_tarefa}", config.nome)

    if atividade.get("tipo") != "assignment":
        return False

    # Clica em Atribuicoes
    try:
        assignments_btn = browser.page.locator(
            'button:has-text("Assignments"), button:has-text("Atribuições"), button:has-text("Atribuicoes")'
        ).first
        await assignments_btn.click(timeout=10000)
    except Exception:
        log("Botao Assignments nao encontrado, tentando via URL...", config.nome)
        await browser.page.goto("https://teams.microsoft.com/_#/school/assignments")
    await asyncio.sleep(5)

    # Debug: mostra todos os frames
    all_frames = browser.page.frames
    log(f"  Frames encontrados: {len(all_frames)}", config.nome)
    for f in all_frames:
        if f.url and f.url != "about:blank":
            log(f"  Frame URL: {f.url[:100]}", config.nome)

    # Busca frame de assignments
    frame = None
    for f in browser.page.frames:
        url_lower = f.url.lower()
        if "assignments" in url_lower or "classroom" in url_lower or "edu" in url_lower:
            frame = f
            log(f"  Frame de assignments encontrado!", config.nome)
            break

    # Se nao achou frame, usa a pagina principal
    if not frame:
        log("  Nenhum frame de assignments, usando pagina principal", config.nome)
        frame = browser.page

    # Screenshot para debug
    await browser.page.screenshot(path=str(data_dir / "assignments_page.png"))

    # Busca em cada aba
    tarefa_encontrada = False
    for tab in ["Em breve", "Em atraso", "Upcoming", "Past due", "Assigned", "Atribuído"]:
        if not tarefa_encontrada:
            try:
                tab_btn = frame.locator(f'text="{tab}"').first
                await tab_btn.click(timeout=5000)
                await asyncio.sleep(3)

                if nome_tarefa and await buscar_tarefa_no_frame(frame, nome_tarefa):
                    await asyncio.sleep(4)
                    log(f"  Tarefa encontrada em {tab}!", config.nome)
                    tarefa_encontrada = True
                    break
            except Exception:
                pass

    if not tarefa_encontrada:
        log(f"Tarefa nao encontrada: {nome_tarefa} (marcando como processada)", config.nome)
        return "nao_encontrada"

    # Atualiza frame
    for f in browser.page.frames:
        if "assignments" in f.url.lower():
            frame = f
            break

    # Extrai conteudo
    tarefa_info = {"nome": nome_tarefa, "instrucoes": "", "screenshots": []}
    content = await frame.inner_text("body")

    # Parse instrucoes
    for label in ["Instructions", "Instruções", "Instrucoes"]:
        if label in content:
            start = content.find(label) + len(label)
            end = -1
            for end_label in ["Reference materials", "Materiais de referência", "My work", "Meu trabalho"]:
                pos = content.find(end_label)
                if pos != -1:
                    end = pos
                    break
            if end == -1:
                end = start + 500
            tarefa_info["instrucoes"] = content[start:end].strip()
            break

    formato = detectar_formato_resposta(content)
    tarefa_info["formato"] = formato

    # Screenshot da tarefa
    screenshot_path = data_dir / "tarefa_nova.png"
    await browser.page.screenshot(path=str(screenshot_path))
    tarefa_info["screenshots"].append(str(screenshot_path))

    # Processa anexos
    content_lower = content.lower()
    tem_pdf = ".pdf" in content_lower
    tem_imagem = any(ext in content_lower for ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"])

    if tem_pdf:
        log("PDF encontrado, abrindo preview...", config.nome)
        try:
            # Encontra e clica no PDF para abrir preview
            pdf_link = frame.locator('text=/.pdf/i').first
            await pdf_link.click(timeout=10000)
            await asyncio.sleep(5)  # Espera o preview carregar

            for page_num in range(1, MAX_PDF_PAGES + 1):
                ss_path = data_dir / f"pdf_novo_{page_num}.png"
                await browser.page.screenshot(path=str(ss_path))
                tarefa_info["screenshots"].append(str(ss_path))
                log(f"  Screenshot {page_num} do PDF capturado", config.nome)

                # Tenta ir para proxima pagina
                try:
                    next_btn = browser.page.locator(
                        'button[aria-label*="Next"], button[aria-label*="Próxim"], '
                        'button[aria-label*="Proxim"], button[aria-label*="next"], '
                        '[data-icon-name="ChevronRight"], button:has-text(">")'
                    ).first
                    await next_btn.click(timeout=2000)
                    await asyncio.sleep(1)
                except Exception:
                    # Nao tem mais paginas
                    break

            await fechar_preview(browser)
            frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa)
        except Exception as e:
            log(f"  Erro ao processar PDF: {e}", config.nome)
            # Tenta fechar qualquer preview aberto
            try:
                await fechar_preview(browser)
            except Exception:
                pass

    if tem_imagem:
        log("Imagem(ns) encontrada(s), extraindo...", config.nome)
        for ext in [".png", ".jpg", ".jpeg", ".gif"]:
            if ext not in content_lower:
                continue
            try:
                img_links = frame.locator(f'text=/{re.escape(ext)}/i')
                count = await img_links.count()
                for idx in range(min(count, 5)):
                    try:
                        await img_links.nth(idx).click(timeout=5000)
                        await asyncio.sleep(3)
                        ss_path = data_dir / f"img_anexo_{ext.replace('.', '')}_{idx+1}.png"
                        await browser.page.screenshot(path=str(ss_path))
                        tarefa_info["screenshots"].append(str(ss_path))
                        await fechar_preview(browser)
                        await asyncio.sleep(1)
                    except Exception:
                        break
            except Exception:
                pass
        frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa)

    # Processa documentos anexados (abre preview e tira screenshots, como PDF)
    tem_docx_anexo = any(ext in content_lower for ext in [".docx", ".doc"])
    tem_xlsx_anexo = any(ext in content_lower for ext in [".xlsx", ".xls"])

    if tem_docx_anexo or tem_xlsx_anexo:
        log("Documento(s) anexado(s), abrindo preview...", config.nome)
        doc_extensions = []
        if tem_docx_anexo:
            doc_extensions.extend([".docx"])  # Só .docx para evitar duplicatas
        if tem_xlsx_anexo:
            doc_extensions.extend([".xlsx"])

        for ext in doc_extensions:
            if ext not in content_lower:
                continue
            try:
                # Encontra e clica no documento para abrir preview
                doc_link = frame.locator(f'text=/{re.escape(ext)}/i').first
                await doc_link.click(timeout=10000)
                await asyncio.sleep(4)  # Espera o preview carregar

                # Tira screenshots do preview (ate 10 paginas)
                max_doc_pages = 10
                for page_num in range(1, max_doc_pages + 1):
                    ss_path = data_dir / f"doc_{ext.replace('.', '')}_{page_num}.png"
                    await browser.page.screenshot(path=str(ss_path))
                    tarefa_info["screenshots"].append(str(ss_path))
                    log(f"  Screenshot {page_num} do documento capturado", config.nome)

                    # Tenta ir para proxima pagina
                    try:
                        next_btn = browser.page.locator(
                            'button[aria-label*="Next"], button[aria-label*="Próxim"], '
                            'button[aria-label*="Proxim"], button[aria-label*="next"], '
                            '[data-icon-name="ChevronRight"], button:has-text(">")'
                        ).first
                        await next_btn.click(timeout=2000)
                        await asyncio.sleep(1)
                    except Exception:
                        # Nao tem mais paginas ou botao nao encontrado
                        break

                # Fecha o preview
                await fechar_preview(browser)
                frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa)

            except Exception as e:
                log(f"  Erro ao processar documento {ext}: {e}", config.nome)
                # Tenta fechar qualquer preview aberto
                try:
                    await fechar_preview(browser)
                except Exception:
                    pass

        frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa)

    # Resolve com Claude
    log("Enviando para Claude...", config.nome)
    resposta = resolver_com_claude(tarefa_info, config.anthropic_key)

    if not resposta:
        log("Falha ao resolver", config.nome)
        return False

    # Detecta formato
    formato_detectado = detectar_formato_da_resposta(resposta)
    if formato_detectado:
        formato = formato_detectado
    log(f"Formato final: {formato}", config.nome)

    resposta = remover_marcador_formato(resposta)

    # Cria arquivos
    arquivos = []
    if formato == "zip":
        arquivos = extrair_projeto_multi_arquivo(resposta, nome_tarefa, data_dir)
    elif formato in ["html"] + FORMATOS_CODIGO:
        arquivos = extrair_multiplos_arquivos(resposta, formato, nome_tarefa, data_dir)

    if not arquivos and formato not in ["texto"]:
        path = criar_arquivo_resposta(resposta, nome_tarefa, formato, data_dir)
        arquivos = [path]

    if not arquivos and formato == "texto":
        path = str(data_dir / "resposta_nova.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(resposta)
        arquivos = [path]

    # Atualiza frame antes de enviar
    for f in browser.page.frames:
        if "assignments" in f.url.lower():
            frame = f
            break

    # Clica em Adicionar trabalho
    try:
        add_work = frame.locator('text=/Add work/i, text=/Adicionar trabalho/i').first
        await add_work.click(timeout=5000)
        await asyncio.sleep(2)
    except Exception:
        pass

    # Upload ou texto
    if formato != "texto":
        try:
            file_input = frame.locator('input[type="file"]').first
            await file_input.set_input_files(arquivos)
            await asyncio.sleep(3)
        except Exception:
            try:
                text_area = frame.locator('textarea, [contenteditable="true"]').first
                await text_area.fill(resposta[:5000])
            except Exception:
                return False
    else:
        try:
            text_area = frame.locator('textarea, [contenteditable="true"]').first
            await text_area.fill(resposta[:5000])
        except Exception:
            try:
                file_input = frame.locator('input[type="file"]').first
                await file_input.set_input_files(arquivos)
                await asyncio.sleep(2)
            except Exception:
                return False

    # Submit
    try:
        submit = frame.locator(
            'button:has-text("Turn in late"), button:has-text("Entregar com atraso"), '
            'button:has-text("Turn in"), button:has-text("Entregar")'
        ).first
        await submit.click(timeout=5000)
        await asyncio.sleep(2)

        try:
            confirm = browser.page.locator(
                'button:has-text("Turn in late"), button:has-text("Entregar com atraso"), '
                'button:has-text("Turn in"), button:has-text("Entregar")'
            ).first
            await confirm.click(timeout=3000)
        except Exception:
            pass

        log("Resposta enviada com sucesso!", config.nome)

        # Screenshot de comprovacao
        comp_name = re.sub(r'[^\w]', '', nome_tarefa)[:30]
        comp_path = str(data_dir / f"comprovacao_{comp_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        await browser.page.screenshot(path=comp_path)

        # Notificacao por email
        if config.smtp_email and config.notification_email:
            try:
                notifier = EmailNotifier(
                    smtp_email=config.smtp_email,
                    smtp_password=config.smtp_password,
                    to_email=config.notification_email,
                )
                notifier.notify_tarefa_resolvida(nome_tarefa, disciplina, resposta)
            except Exception:
                pass

        # Volta
        await asyncio.sleep(2)
        try:
            back_btn = browser.page.locator('button[aria-label*="Back"], button[aria-label*="Voltar"]').first
            await back_btn.click(timeout=3000)
        except Exception:
            try:
                assignments_btn = browser.page.locator(
                    'button:has-text("Assignments"), button:has-text("Atribuições"), button:has-text("Atribuicoes")'
                ).first
                await assignments_btn.click(timeout=5000)
            except Exception:
                await browser.page.keyboard.press("Escape")
                await asyncio.sleep(1)

        await asyncio.sleep(3)
        return True

    except Exception as e:
        log(f"Erro ao enviar: {e}", config.nome)
        return False


async def ciclo_monitoramento_cliente(config: ClientConfig) -> dict:
    """
    Executa um ciclo de monitoramento para um cliente.
    Retorna dict com resultados: {success: int, error: int, tasks: list}
    """
    resultado = {"success": 0, "error": 0, "tasks": []}

    log(f"Iniciando ciclo de monitoramento", config.nome)

    browser = TeamsBrowser(
        auth_state_path=config.auth_state_path,
        teams_email=config.teams_email,
        teams_password=config.teams_password,
    )
    await browser.start(headless=True)

    try:
        log("Conectando ao Teams...", config.nome)
        await browser.page.goto("https://teams.microsoft.com")
        await browser.page.wait_for_load_state("networkidle")
        await asyncio.sleep(8)

        page_content = await browser.page.inner_text("body")
        if "Sign in" in page_content or "Entrar" in page_content:
            log("Sessao expirada, fazendo login...", config.nome)
            login_ok = await browser.login()
            if not login_ok:
                log("Login falhou! Abortando ciclo.", config.nome)
                resultado["error"] += 1
                resultado["tasks"].append({
                    "name": "Login",
                    "discipline": "",
                    "status": "error",
                    "error": "Falha no login do Teams",
                })
                return resultado
            await asyncio.sleep(5)

        processadas = carregar_processadas(config.processadas_path)
        atividades = await verificar_activity(browser, config.data_dir, config.nome)
        novas = [a for a in atividades if a.get("id") not in processadas]

        if not novas:
            log("Nenhuma atividade nova!", config.nome)
        else:
            log(f"{len(novas)} atividade(s) nova(s)", config.nome)

            for atividade in novas:
                try:
                    res = await processar_nova_atividade(browser, atividade, config)
                    if res:
                        processadas.add(atividade["id"])
                        salvar_processadas(processadas, config.processadas_path)

                        task_result = {
                            "name": atividade.get("nome", ""),
                            "discipline": atividade.get("disciplina", ""),
                            "status": "success" if res is True else "skipped",
                        }
                        resultado["tasks"].append(task_result)
                        resultado["success"] += 1
                    else:
                        resultado["tasks"].append({
                            "name": atividade.get("nome", ""),
                            "discipline": atividade.get("disciplina", ""),
                            "status": "error",
                            "error": "Falha ao processar",
                        })
                        resultado["error"] += 1
                except Exception as e:
                    log(f"Erro ao processar: {e}", config.nome)
                    resultado["tasks"].append({
                        "name": atividade.get("nome", ""),
                        "discipline": atividade.get("disciplina", ""),
                        "status": "error",
                        "error": str(e),
                    })
                    resultado["error"] += 1

                await asyncio.sleep(5)

    except Exception as e:
        log(f"Erro no ciclo: {e}", config.nome)
        resultado["error"] += 1
    finally:
        await browser.close()

    log(f"Ciclo finalizado: {resultado['success']} ok, {resultado['error']} erros", config.nome)
    return resultado
