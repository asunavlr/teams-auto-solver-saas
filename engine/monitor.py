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
from engine.agent import TeamsAgent
from engine.file_searcher import FileSearcher, detectar_arquivo_externo

MAX_PDF_PAGES = 15

# Agente global (inicializado por cliente)
_current_agent: TeamsAgent = None


class ClientConfig:
    """Configuracao de um cliente para monitoramento."""

    def __init__(self, client_id: int, nome: str, teams_email: str,
                 teams_password: str, anthropic_key: str,
                 data_dir: Path, check_interval: int = 60,
                 smtp_email: str = "", smtp_password: str = "",
                 notification_email: str = "", whatsapp: str = ""):
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
        self.whatsapp = whatsapp

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


def carregar_processadas(path: Path) -> dict:
    """Carrega atividades processadas. Retorna dict {id: {nome, disciplina}}."""
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
            # Compatibilidade: se for lista antiga, converte pra dict
            if isinstance(data, list):
                return {id: {"nome": "", "disciplina": ""} for id in data}
            return data
    return {}


def salvar_processadas(processadas: dict, path: Path):
    """Salva atividades processadas como dict {id: {nome, disciplina}}."""
    with open(path, "w") as f:
        json.dump(processadas, f, ensure_ascii=False, indent=2)


def carregar_tentativas_falhas(path: Path) -> dict:
    """Carrega contador de tentativas falhas. Retorna dict {id: tentativas}."""
    falhas_path = path.parent / "tentativas_falhas.json"
    if falhas_path.exists():
        with open(falhas_path, "r") as f:
            return json.load(f)
    return {}


def salvar_tentativas_falhas(tentativas: dict, path: Path):
    """Salva contador de tentativas falhas."""
    falhas_path = path.parent / "tentativas_falhas.json"
    with open(falhas_path, "w") as f:
        json.dump(tentativas, f, ensure_ascii=False, indent=2)


MAX_TENTATIVAS_NOT_FOUND = 3  # Quantas vezes tentar antes de marcar como processada


async def verificar_activity(browser, data_dir: Path, client_name: str = "", max_tentativas: int = 3, agent: TeamsAgent = None) -> list:
    """Verifica a aba Activity e retorna novas atividades.

    Se não encontrar atividades, tenta novamente até max_tentativas vezes,
    esperando 10 segundos entre cada tentativa.

    Args:
        agent: TeamsAgent opcional para navegacao resiliente (fallback para Vision)
    """
    log("Acessando Activity...", client_name)

    # Usa o agente se disponivel (com fallback inteligente)
    if agent:
        clicked = await agent.clicar("atividade")
        if not clicked:
            log("Falha ao clicar em Activity via agente", client_name)
            return []
    else:
        # Fallback: tentativa manual com seletores CSS
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
                    # Cria ID unico com nome + disciplina + prazo para evitar duplicatas
                    id_string = (
                        atividade["nome"] +
                        atividade.get("disciplina", "") +
                        atividade.get("prazo", "") +
                        atividade.get("data", "")
                    )
                    atividade["id"] = hashlib.md5(id_string.encode()).hexdigest()
                    atividades.append(atividade)
                    disciplina = atividade.get('disciplina', 'sem disciplina')
                    log(f"  Encontrada: {atividade['nome']} | {disciplina}", client_name)

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


async def buscar_tarefa_no_frame(frame, nome_tarefa: str, disciplina: str = "", agent: TeamsAgent = None) -> bool:
    """Busca e clica na tarefa pelo nome, considerando a disciplina se fornecida.

    Se CSS falhar e agent estiver disponivel, usa Vision como fallback.
    """
    nome_limpo = re.sub(r'[()\\/*+?\[\]{}|^$.]', '', nome_tarefa).strip()

    # Se tem disciplina, tenta encontrar a tarefa que está associada a ela
    if disciplina:
        try:
            # Pega o conteudo da pagina para verificar contexto
            page_content = await frame.inner_text("body")

            # Busca todas as tarefas com o nome
            resultados = frame.locator(f'text=/{re.escape(nome_limpo)}/i')
            count = await resultados.count()

            if count > 1:
                # Se tem mais de uma, tenta achar a que está perto da disciplina
                for idx in range(count):
                    try:
                        elemento = resultados.nth(idx)
                        # Pega o texto do elemento pai para ver se contem a disciplina
                        parent = elemento.locator('xpath=ancestor::*[contains(@class, "assignment") or contains(@class, "item") or contains(@class, "card")]').first
                        parent_text = await parent.inner_text(timeout=2000)

                        # Verifica se a disciplina está no contexto
                        disciplina_curta = disciplina.split("-")[-1].strip() if "-" in disciplina else disciplina
                        if disciplina_curta.lower() in parent_text.lower():
                            await elemento.click(timeout=5000)
                            return True
                    except Exception:
                        continue
        except Exception:
            pass

    # Fallback: busca normal pelo nome
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

    # Fallback: usa Vision se agent disponivel
    if agent:
        logger.warning(f"CSS nao encontrou tarefa '{nome_tarefa}', usando Vision")
        try:
            # Pega primeiras palavras do nome para o prompt
            nome_curto = " ".join(nome_tarefa.split()[:5])
            encontrou = await agent._clicar_com_visao(
                f"Tarefa ou assignment com nome '{nome_curto}' na lista de tarefas"
            )
            if encontrou:
                return True
        except Exception as e:
            logger.error(f"Vision tambem falhou: {e}")

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


async def recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina="", agent: TeamsAgent = None, reabrir_tarefa: bool = False):
    """Recupera o frame de assignments e opcionalmente reabre a tarefa.

    Args:
        reabrir_tarefa: Se True, sempre clica na tarefa para reabri-la
    """
    # Encontra o frame de assignments
    frame = None
    for f in browser.page.frames:
        if "assignments" in f.url.lower():
            frame = f
            break

    if not frame:
        log("  Frame perdido, navegando de volta...")
        assignments_btn = browser.page.locator(
            'button:has-text("Assignments"), button:has-text("Atribuicoes"), button:has-text("Atribuições")'
        ).first
        await assignments_btn.click(timeout=10000)
        await asyncio.sleep(4)

        for f in browser.page.frames:
            if "assignments" in f.url.lower():
                frame = f
                break

    # Se precisa reabrir a tarefa, busca e clica nela
    if frame and reabrir_tarefa:
        log(f"  Reabrindo tarefa: {nome_tarefa[:40]}...")
        for tab in ["Em breve", "Em atraso", "Upcoming", "Past due"]:
            try:
                tab_btn = frame.locator(f'text="{tab}"').first
                await tab_btn.click(timeout=5000)
                await asyncio.sleep(2)
                if await buscar_tarefa_no_frame(frame, nome_tarefa, disciplina, agent):
                    await asyncio.sleep(4)
                    break
            except Exception:
                continue

    return frame


async def processar_nova_atividade(browser, atividade: dict, config: ClientConfig, agent: TeamsAgent = None) -> dict:
    """Processa uma nova atividade para um cliente.

    Retorna dict com:
        - status: 'success', 'skipped', 'not_found', 'group', 'error'
        - format: formato do arquivo (docx, pdf, etc)
        - error: mensagem de erro se houver
    """
    nome_tarefa = atividade.get("nome", "")
    disciplina = atividade.get("disciplina", "")
    data_dir = config.data_dir
    resultado = {"status": "error", "format": "", "error": ""}

    log(f"Processando: {nome_tarefa} | {disciplina}", config.nome)

    if atividade.get("tipo") != "assignment":
        resultado["status"] = "skipped"
        resultado["error"] = "Tipo nao suportado"
        return resultado

    # Detecta atividades OBRIGATORIAMENTE em grupo (pula automaticamente)
    # Só pula se tiver "em grupo", "em equipe", etc. - ignora "pode ser em dupla"
    nome_lower = nome_tarefa.lower()
    frases_grupo_obrigatorio = [
        "trabalho em grupo", "atividade em grupo", "em equipe", "trabalho em equipe",
        "atividade em equipe", "entrega em grupo", "fazer em grupo"
    ]
    if any(frase in nome_lower for frase in frases_grupo_obrigatorio):
        log(f"  Atividade em GRUPO detectada, pulando: {nome_tarefa}", config.nome)
        resultado["status"] = "group"
        return resultado

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

                if nome_tarefa and await buscar_tarefa_no_frame(frame, nome_tarefa, disciplina, agent):
                    await asyncio.sleep(4)
                    log(f"  Tarefa encontrada em {tab}!", config.nome)
                    tarefa_encontrada = True
                    break
            except Exception:
                pass

    if not tarefa_encontrada:
        log(f"Tarefa nao encontrada: {nome_tarefa} (marcando como processada)", config.nome)
        resultado["status"] = "not_found"
        return resultado

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

    # Verifica se é atividade em grupo (no nome OU nas instruções)
    texto_verificar = (nome_tarefa + " " + tarefa_info["instrucoes"]).lower()
    frases_grupo = [
        "atividade em grupo", "trabalho em grupo", "em equipe",
        "atividade em dupla", "trabalho em dupla", "em trio",
        "grupo de ate", "grupo de até", "equipe de ate", "equipe de até",
        "formar grupo", "formar equipe", "formem grupo", "formem equipe"
    ]
    if any(frase in texto_verificar for frase in frases_grupo):
        log(f"  Atividade em GRUPO detectada nas instrucoes, pulando!", config.nome)
        await fechar_preview(browser)
        resultado["status"] = "group"
        return resultado

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

            # Espera o preview carregar completamente
            log("  Aguardando preview carregar...", config.nome)

            # Espera a pagina estabilizar
            try:
                await browser.page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass

            # Espera adicional para garantir que o conteudo renderizou
            await asyncio.sleep(8)

            # Verifica se ainda tem loading spinner
            try:
                loading = browser.page.locator('[class*="loading"], [class*="spinner"], [class*="progress"]').first
                await loading.wait_for(state="hidden", timeout=10000)
            except Exception:
                pass

            await asyncio.sleep(2)  # Espera final

            ultimo_hash = None
            for page_num in range(1, MAX_PDF_PAGES + 1):
                ss_path = data_dir / f"pdf_novo_{page_num}.png"
                await browser.page.screenshot(path=str(ss_path))

                # Verifica se o screenshot é igual ao anterior (fim do documento)
                with open(ss_path, "rb") as f:
                    current_hash = hashlib.md5(f.read()).hexdigest()

                if current_hash == ultimo_hash:
                    log(f"  Pagina {page_num} igual a anterior, fim do PDF", config.nome)
                    # Remove o screenshot duplicado
                    ss_path.unlink()
                    break

                ultimo_hash = current_hash
                tarefa_info["screenshots"].append(str(ss_path))
                log(f"  Screenshot {page_num} do PDF capturado", config.nome)

                # Navega para proxima secao do documento (15 scrolls/setas)
                try:
                    for _ in range(15):
                        await browser.page.keyboard.press("ArrowDown")
                        await asyncio.sleep(0.1)
                    # Scroll adicional para garantir
                    await browser.page.mouse.wheel(0, 500)
                    await asyncio.sleep(1)
                except Exception:
                    break

            await fechar_preview(browser)
            frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)
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
        frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)

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
                ultimo_hash = None
                for page_num in range(1, max_doc_pages + 1):
                    ss_path = data_dir / f"doc_{ext.replace('.', '')}_{page_num}.png"
                    await browser.page.screenshot(path=str(ss_path))

                    # Verifica se o screenshot é igual ao anterior (fim do documento)
                    with open(ss_path, "rb") as f:
                        current_hash = hashlib.md5(f.read()).hexdigest()

                    if current_hash == ultimo_hash:
                        log(f"  Pagina {page_num} igual a anterior, fim do documento", config.nome)
                        ss_path.unlink()
                        break

                    ultimo_hash = current_hash
                    tarefa_info["screenshots"].append(str(ss_path))
                    log(f"  Screenshot {page_num} do documento capturado", config.nome)

                    # Navega para proxima secao (15 scrolls/setas)
                    try:
                        for _ in range(15):
                            await browser.page.keyboard.press("ArrowDown")
                            await asyncio.sleep(0.1)
                        await browser.page.mouse.wheel(0, 500)
                        await asyncio.sleep(1)
                    except Exception:
                        break

                # Fecha o preview
                await fechar_preview(browser)
                frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)

            except Exception as e:
                log(f"  Erro ao processar documento {ext}: {e}", config.nome)
                # Tenta fechar qualquer preview aberto
                try:
                    await fechar_preview(browser)
                except Exception:
                    pass

        frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)

    # Verifica se instrucoes referenciam arquivo externo
    arquivo_externo = detectar_arquivo_externo(tarefa_info.get("instrucoes", ""))
    if arquivo_externo and agent:
        log(f"Arquivo externo detectado: {arquivo_externo}", config.nome)
        log(f"Buscando na turma: {disciplina}", config.nome)

        try:
            searcher = FileSearcher(browser, agent, data_dir)
            resultado_busca = await searcher.buscar_arquivo(
                nome_arquivo=arquivo_externo,
                disciplina=disciplina
            )

            if resultado_busca["encontrado"]:
                log(f"Arquivo encontrado! Adicionando conteudo as instrucoes...", config.nome)

                # Adiciona conteudo do arquivo as instrucoes
                conteudo_arquivo = resultado_busca.get("conteudo", "")
                if conteudo_arquivo:
                    tarefa_info["instrucoes"] = f"""
INSTRUCOES DA TAREFA:
{tarefa_info.get("instrucoes", "")}

CONTEUDO DO ARQUIVO {arquivo_externo}:
{conteudo_arquivo}
"""
                # Adiciona screenshots do arquivo
                tarefa_info["screenshots"].extend(resultado_busca.get("screenshots", []))

                # Volta para Assignments e reabre a tarefa
                log("Voltando para Assignments...", config.nome)
                await agent.clicar("tarefas")  # Clica em Assignments
                await asyncio.sleep(3)

                # Reabre a tarefa especifica (reabrir_tarefa=True força clicar na tarefa)
                frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent, reabrir_tarefa=True)
                if frame:
                    log("Tarefa reaberta com sucesso!", config.nome)
                else:
                    log("AVISO: Nao conseguiu reabrir a tarefa", config.nome)
            else:
                # Arquivo externo nao encontrado - nao da pra resolver a tarefa
                log(f"Arquivo externo nao encontrado: {resultado_busca.get('erro', 'erro desconhecido')}", config.nome)
                log("Pulando tarefa - sera tentada novamente no proximo ciclo", config.nome)
                resultado["status"] = "skipped"
                resultado["error"] = f"Arquivo externo nao encontrado: {arquivo_externo}"
                return resultado

        except Exception as e:
            log(f"Erro ao buscar arquivo externo: {e}", config.nome)
            log("Pulando tarefa - sera tentada novamente no proximo ciclo", config.nome)
            resultado["status"] = "skipped"
            resultado["error"] = f"Erro ao buscar arquivo: {str(e)}"
            return resultado

    # Resolve com Claude
    log("Enviando para Claude...", config.nome)
    resposta = resolver_com_claude(tarefa_info, config.anthropic_key)

    if not resposta:
        log("Falha ao resolver", config.nome)
        resultado["status"] = "error"
        resultado["format"] = formato
        resultado["error"] = "Claude nao retornou resposta"
        return resultado

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
                resultado["status"] = "error"
                resultado["format"] = formato
                resultado["error"] = "Falha ao anexar arquivo"
                return resultado
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
                resultado["status"] = "error"
                resultado["format"] = formato
                resultado["error"] = "Falha ao preencher texto"
                return resultado

    # Submit
    try:
        submit = frame.locator(
            'button:has-text("Turn in again"), button:has-text("Entregar novamente"), '
            'button:has-text("Turn in late"), button:has-text("Entregar com atraso"), '
            'button:has-text("Turn in"), button:has-text("Entregar")'
        ).first
        await submit.click(timeout=5000)
        await asyncio.sleep(2)

        try:
            confirm = browser.page.locator(
                'button:has-text("Turn in again"), button:has-text("Entregar novamente"), '
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
        resultado["status"] = "success"
        resultado["format"] = formato
        return resultado

    except Exception as e:
        log(f"Erro ao enviar: {e}", config.nome)
        resultado["status"] = "error"
        resultado["format"] = formato
        resultado["error"] = str(e)
        return resultado


def update_client_status(client_id: int, status: str, action: str = "", error: str = ""):
    """Atualiza status em tempo real do cliente (thread-safe)."""
    try:
        from web import create_app, db
        from web.models import ClientStatus

        app = create_app()
        with app.app_context():
            ClientStatus.set_status(client_id, status, action, error)
    except Exception as e:
        logger.debug(f"Erro ao atualizar status do cliente {client_id}: {e}")


async def ciclo_monitoramento_cliente(config: ClientConfig) -> dict:
    """
    Executa um ciclo de monitoramento para um cliente.
    Retorna dict com resultados: {success: int, error: int, tasks: list}
    """
    global _current_agent

    resultado = {"success": 0, "error": 0, "tasks": []}

    log(f"Iniciando ciclo de monitoramento", config.nome)
    update_client_status(config.client_id, "running", "Iniciando monitoramento...")

    browser = TeamsBrowser(
        auth_state_path=config.auth_state_path,
        teams_email=config.teams_email,
        teams_password=config.teams_password,
    )
    # Para testes locais, mude para headless=False
    import os
    headless = os.environ.get("HEADLESS", "true").lower() != "false"
    await browser.start(headless=headless)

    # Cria agente de navegacao inteligente
    agent = TeamsAgent(browser.page, config.anthropic_key)
    _current_agent = agent

    try:
        log("Conectando ao Teams...", config.nome)
        update_client_status(config.client_id, "running", "Conectando ao Teams...")
        await browser.page.goto("https://teams.microsoft.com")
        log("Pagina carregada, aguardando estabilizar...", config.nome)
        try:
            await browser.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            log("Timeout no networkidle, continuando...", config.nome)
        await asyncio.sleep(8)
        log("Pronto para verificar atividades...", config.nome)

        page_content = await browser.page.inner_text("body")
        if "Sign in" in page_content or "Entrar" in page_content:
            log("Sessao expirada, fazendo login...", config.nome)
            update_client_status(config.client_id, "running", "Fazendo login...")
            login_ok = await browser.login()
            if not login_ok:
                log("Login falhou! Abortando ciclo.", config.nome)
                update_client_status(config.client_id, "error", "", "Falha no login")
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
        update_client_status(config.client_id, "running", "Verificando atividades...")
        atividades = await verificar_activity(browser, config.data_dir, config.nome, agent=agent)
        novas = [a for a in atividades if a.get("id") not in processadas]

        # Carrega contador de tentativas falhas
        tentativas_falhas = carregar_tentativas_falhas(config.processadas_path)

        if not novas:
            log("Nenhuma atividade nova!", config.nome)
            update_client_status(config.client_id, "idle", "Nenhuma atividade nova")
        else:
            log(f"{len(novas)} atividade(s) nova(s)", config.nome)

            for atividade in novas:
                nome_tarefa = atividade.get("nome", "")[:50]
                atividade_id = atividade["id"]
                update_client_status(config.client_id, "running", f"Processando: {nome_tarefa}...")
                try:
                    res = await processar_nova_atividade(browser, atividade, config, agent)

                    # Lógica de marcação como processada
                    if res["status"] == "not_found":
                        # Incrementa contador de tentativas falhas
                        tentativas_falhas[atividade_id] = tentativas_falhas.get(atividade_id, 0) + 1
                        tentativas = tentativas_falhas[atividade_id]

                        if tentativas >= MAX_TENTATIVAS_NOT_FOUND:
                            # Atingiu limite, marca como processada
                            log(f"Atividade nao encontrada {tentativas}x, marcando como processada", config.nome)
                            processadas[atividade_id] = {
                                "nome": atividade.get("nome", ""),
                                "disciplina": atividade.get("disciplina", ""),
                            }
                            salvar_processadas(processadas, config.processadas_path)
                            # Remove do contador
                            del tentativas_falhas[atividade_id]
                        else:
                            log(f"Atividade nao encontrada (tentativa {tentativas}/{MAX_TENTATIVAS_NOT_FOUND}), vai tentar novamente", config.nome)

                        salvar_tentativas_falhas(tentativas_falhas, config.processadas_path)

                    elif res["status"] != "error":
                        # Sucesso, skipped, group - marca como processada
                        processadas[atividade_id] = {
                            "nome": atividade.get("nome", ""),
                            "disciplina": atividade.get("disciplina", ""),
                        }
                        salvar_processadas(processadas, config.processadas_path)
                        # Remove do contador de falhas se existia
                        if atividade_id in tentativas_falhas:
                            del tentativas_falhas[atividade_id]
                            salvar_tentativas_falhas(tentativas_falhas, config.processadas_path)

                    task_result = {
                        "name": atividade.get("nome", ""),
                        "discipline": atividade.get("disciplina", ""),
                        "status": res["status"],
                        "format": res.get("format", ""),
                        "error": res.get("error", ""),
                    }
                    resultado["tasks"].append(task_result)

                    if res["status"] == "success":
                        resultado["success"] += 1
                    elif res["status"] == "error":
                        resultado["error"] += 1
                    # skipped, not_found, group não contam como erro

                except Exception as e:
                    log(f"Erro ao processar: {e}", config.nome)
                    resultado["tasks"].append({
                        "name": atividade.get("nome", ""),
                        "discipline": atividade.get("disciplina", ""),
                        "status": "error",
                        "format": "",
                        "error": str(e),
                    })
                    resultado["error"] += 1

                await asyncio.sleep(5)

    except Exception as e:
        log(f"Erro no ciclo: {e}", config.nome)
        update_client_status(config.client_id, "error", "", str(e))
        resultado["error"] += 1
    finally:
        await browser.close()
        if resultado["error"] == 0:
            update_client_status(config.client_id, "idle", f"Ciclo concluido: {resultado['success']} tarefas")
        else:
            update_client_status(config.client_id, "error", "", f"{resultado['error']} erro(s)")

    # Log das estatisticas do agente e salva custos
    if agent:
        stats = agent.get_stats()
        if stats["vision_calls"] > 0:
            custo = stats['estimated_cost']
            log(f"Agente usou Vision {stats['vision_calls']}x (custo estimado: R${custo:.2f})", config.nome)
            # Salva custo no banco
            try:
                from web.models import ApiCost
                ApiCost.registrar(
                    client_id=config.client_id,
                    tipo="vision",
                    custo=custo,
                    descricao=f"Vision usado {stats['vision_calls']}x no ciclo"
                )
            except Exception as e:
                log(f"Erro ao salvar custo: {e}", config.nome)

    log(f"Ciclo finalizado: {resultado['success']} ok, {resultado['error']} erros", config.nome)
    return resultado
