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
    analisar_intencao_tarefa,
    detectar_formato_resposta,
    detectar_formato_da_resposta,
    remover_marcador_formato,
    criar_arquivo_resposta,
    extrair_multiplos_arquivos,
    extrair_projeto_multi_arquivo,
    criar_projeto_android,
    FORMATOS_CODIGO,
)
from engine.notifier import EmailNotifier
from engine.agent import TeamsAgent
from engine.file_searcher import FileSearcher, detectar_arquivo_externo
from engine.file_extractor import extrair_conteudo_arquivo

MAX_PDF_PAGES = 15

# Agente global (inicializado por cliente)
_current_agent: TeamsAgent = None


class ClientConfig:
    """Configuracao de um cliente para monitoramento."""

    def __init__(self, client_id: int, nome: str, teams_email: str,
                 teams_password: str, anthropic_key: str,
                 data_dir: Path, check_interval: int = 60,
                 smtp_email: str = "", smtp_password: str = "",
                 notification_email: str = "", whatsapp: str = "",
                 limite_tarefas: int = None, tarefas_mes: int = 0):
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
        self.limite_tarefas = limite_tarefas  # None = ilimitado
        self.tarefas_mes = tarefas_mes  # Contador atual

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

            # Notificacoes que NAO sao assignments (posts, comentarios, etc.)
            eh_post = (
                "publicou em" in line or "posted in" in line or
                "publicou uma nova" in line or "posted a new post" in line or
                "respondeu a" in line or "replied to" in line or
                "mencionou você" in line or "mentioned you" in line or
                "curtiu" in line or "liked" in line or
                "editou uma postagem" in line or "edited a post" in line or
                "comentou em" in line or "commented on" in line
            )
            if eh_post:
                i += 1
                continue

            # Detecta em portugues e ingles
            detectou_nova = (
                "adicionou uma tarefa" in line or
                "added an assignment" in line or
                "posted an assignment" in line or
                "posted a new assignment" in line
            )
            detectou_atualizada = (
                "atualizou uma tarefa" in line or
                "updated an assignment" in line
            )

            if detectou_nova or detectou_atualizada:
                # Extrai nome do professor (antes do verbo)
                professor = line
                for termo in [" adicion", " atualiz", " added", " updated", " posted"]:
                    if termo in line:
                        professor = line.split(termo)[0].strip()
                        break

                atividade = {
                    "tipo": "assignment",
                    "professor": professor,
                    "acao": "nova" if detectou_nova else "atualizada"
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

        # Deduplica por ID (mesmo nome+disciplina+prazo+data gera mesmo hash)
        vistos = set()
        atividades_unicas = []
        for a in atividades:
            if a["id"] not in vistos:
                vistos.add(a["id"])
                atividades_unicas.append(a)
        atividades = atividades_unicas

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


async def _clicar_em_pagina_ou_frames(browser, seletores: list, timeout: int = 3000, frames_primeiro: bool = True, somente_frames: bool = False) -> bool:
    """
    Tenta clicar usando seletores nos frames E/ou na pagina principal.

    Args:
        frames_primeiro: Tenta iframes de assignments antes da pagina principal
        somente_frames: Se True, ignora a pagina principal (evita clicar em elementos errados)
    """
    # Filtra frames relevantes (assignments/onenote)
    frames_assignments = [
        f for f in browser.page.frames
        if f != browser.page.main_frame and (
            "assignments" in f.url.lower() or
            "onenote" in f.url.lower() or
            f.url != browser.page.url
        )
    ]

    alvos = []
    if somente_frames:
        alvos = frames_assignments
    elif frames_primeiro:
        alvos = frames_assignments + [browser.page]
    else:
        alvos = [browser.page] + frames_assignments

    for alvo in alvos:
        for selector in seletores:
            try:
                await alvo.click(selector, timeout=timeout)
                return True
            except Exception:
                continue

    return False


async def baixar_arquivo_do_teams(browser, agent, config, data_dir: Path) -> Path | None:
    """
    Tenta baixar o arquivo que esta em preview no Teams.

    Estrategia 1: Botao de download na toolbar do preview
    Estrategia 2: Fecha preview, menu "..." ao lado do arquivo, Download

    Returns:
        Path do arquivo baixado ou None se falhou
    """
    downloads_dir = data_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    # Estrategia 1: Botao de download no preview
    log("  Tentando download via botao do preview...", config.nome)
    try:
        async with browser.page.expect_download(timeout=15000) as download_info:
            clicou = await _clicar_em_pagina_ou_frames(
                browser, agent.SELECTORS.get("download_preview", [])
            ) if agent else False

            # Fallback Vision
            if not clicou and agent:
                log("  CSS falhou, tentando Vision para download...", config.nome)
                clicou = await agent._clicar_com_visao(
                    agent.DESCRICOES["download_preview"]
                )

            if not clicou:
                raise Exception("Nenhum botao de download encontrado")

        download = await download_info.value
        filepath = downloads_dir / download.suggested_filename
        await download.save_as(str(filepath))
        log(f"  Download concluido: {filepath.name}", config.nome)
        return filepath

    except Exception as e:
        log(f"  Estrategia 1 (botao preview) falhou: {e}", config.nome)

    # Estrategia 1b: "More actions" na toolbar do preview → Download
    log("  Tentando 'More actions' na toolbar do preview...", config.nome)
    try:
        # Clica em "More actions" / "..." na toolbar do preview
        more_actions_selectors = [
            'button[aria-label="More actions"]',
            'button[aria-label="Mais ações"]',
            'button[aria-label="Mais acoes"]',
            'button[title="More actions"]',
        ]
        clicou_more = await _clicar_em_pagina_ou_frames(
            browser, more_actions_selectors, frames_primeiro=False
        )

        if not clicou_more and agent:
            clicou_more = await agent._clicar_com_visao(
                "Botao 'More actions' ou '...' na TOOLBAR SUPERIOR do preview do documento (ao lado de Print e Close)"
            )

        if clicou_more:
            await asyncio.sleep(2)

            # Agora clica em Download no menu dropdown
            async with browser.page.expect_download(timeout=15000) as download_info:
                clicou_dl = await _clicar_em_pagina_ou_frames(
                    browser, agent.SELECTORS.get("download_menu_item", []) if agent else [],
                    frames_primeiro=False
                )

                if not clicou_dl and agent:
                    clicou_dl = await agent._clicar_com_visao(
                        "Opcao 'Download' no menu que acabou de abrir na toolbar do preview"
                    )

                if not clicou_dl:
                    raise Exception("Download nao encontrado no menu More actions")

            download = await download_info.value
            filepath = downloads_dir / download.suggested_filename
            await download.save_as(str(filepath))
            log(f"  Download concluido (via More actions): {filepath.name}", config.nome)
            return filepath

    except Exception as e:
        log(f"  Estrategia 1b (More actions) falhou: {e}", config.nome)

    # Estrategia 2: Menu tres pontos (ao lado do arquivo na tarefa)
    log("  Tentando download via menu tres pontos...", config.nome)
    try:
        # Fecha o preview primeiro
        await fechar_preview(browser)
        await asyncio.sleep(2)

        # Tenta clicar no "..." ao lado do arquivo (SOMENTE em frames de assignments)
        clicou_menu = False
        if agent:
            clicou_menu = await _clicar_em_pagina_ou_frames(
                browser, agent.SELECTORS.get("menu_tres_pontos", []),
                somente_frames=True
            )

            if not clicou_menu:
                log("  CSS falhou para menu, tentando Vision...", config.nome)
                clicou_menu = await agent._clicar_com_visao(
                    "Botao de tres pontos (...) que fica DENTRO da secao 'Reference materials' ao lado direito do nome do arquivo anexado (PDF/DOCX/XLSX). NAO clique nos tres pontos do cabecalho do Activity."
                )

        if not clicou_menu:
            raise Exception("Menu tres pontos nao encontrado")

        await asyncio.sleep(2)

        # Clica em Download no menu dropdown
        async with browser.page.expect_download(timeout=15000) as download_info:
            clicou_download = await _clicar_em_pagina_ou_frames(
                browser, agent.SELECTORS.get("download_menu_item", [])
            ) if agent else False

            if not clicou_download and agent:
                log("  CSS falhou para Download no menu, tentando Vision...", config.nome)
                clicou_download = await agent._clicar_com_visao(
                    "Opcao 'Download' ou 'Baixar' no menu popup/dropdown que apareceu. Pode conter opcoes como Open, Download, Rename, etc."
                )

            if not clicou_download:
                raise Exception("Item Download no menu nao encontrado")

        download = await download_info.value
        filepath = downloads_dir / download.suggested_filename
        await download.save_as(str(filepath))
        log(f"  Download concluido (via menu): {filepath.name}", config.nome)
        return filepath

    except Exception as e:
        log(f"  Estrategia 2 (menu tres pontos) falhou: {e}", config.nome)

    log("  Todas as estrategias de download falharam", config.nome)
    return None


def limpar_downloads(data_dir: Path):
    """Remove arquivos temporarios de download."""
    downloads_dir = data_dir / "downloads"
    if downloads_dir.exists():
        import shutil
        try:
            shutil.rmtree(downloads_dir)
            logger.debug(f"Diretorio de downloads removido: {downloads_dir}")
        except Exception as e:
            logger.debug(f"Erro ao limpar downloads: {e}")


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
    resultado = {"status": "error", "format": "", "error": "", "instrucoes": "", "resposta": "", "arquivos": []}

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

    # Verifica se esta dentro de uma tarefa (precisa voltar para a lista)
    # Detecta se esta dentro de tarefa verificando se as abas existem
    abas_visiveis = False
    for tab_test in ["Upcoming", "Past due", "Em breve", "Em atraso"]:
        try:
            tab_element = frame.locator(f'text="{tab_test}"').first
            await tab_element.wait_for(timeout=2000, state="visible")
            abas_visiveis = True
            break
        except Exception:
            continue

    if not abas_visiveis:
        log("  Abas nao visiveis, tentando voltar para lista...", config.nome)
        voltou = False

        # Tenta CSS primeiro (frame e pagina principal)
        for contexto in [frame, browser.page]:
            if voltou:
                break
            try:
                back_btn = contexto.locator(
                    'button[aria-label*="Back"], button[aria-label*="Voltar"], '
                    'button:has-text("Back"), button:has-text("Voltar"), '
                    '[data-tid="back-button"], [aria-label*="back"]'
                ).first
                await back_btn.click(timeout=2000)
                log("  Voltando via CSS...", config.nome)
                voltou = True
            except Exception:
                continue

        # Fallback 1: Vision para encontrar botao de voltar
        if not voltou and agent:
            log("  CSS falhou, usando Vision para voltar...", config.nome)
            voltou = await agent._clicar_com_visao(
                "Botao de voltar (seta para esquerda ou 'Back') no topo da pagina para voltar a lista de tarefas"
            )

        # Fallback 2: Volta para Activity e depois clica em Assignments novamente
        if not voltou and agent:
            log("  Vision falhou, resetando via Activity...", config.nome)
            if await agent.clicar("atividade"):
                await asyncio.sleep(3)
                # Clica em Assignments de novo
                try:
                    assignments_btn = browser.page.locator(
                        'button:has-text("Assignments"), button:has-text("Atribuições"), button:has-text("Atribuicoes")'
                    ).first
                    await assignments_btn.click(timeout=5000)
                    voltou = True
                    log("  Reset via Activity funcionou!", config.nome)
                    await asyncio.sleep(4)
                except Exception:
                    pass

        if voltou:
            await asyncio.sleep(4)
            # Atualiza o frame apos voltar
            for f in browser.page.frames:
                if "assignments" in f.url.lower():
                    frame = f
                    break
            # Screenshot apos voltar
            await browser.page.screenshot(path=str(data_dir / "after_back.png"))

    # Busca em cada aba
    tarefa_encontrada = False
    abas_tentadas = 0
    for tab in ["Em breve", "Em atraso", "Upcoming", "Past due", "Assigned", "Atribuído"]:
        if not tarefa_encontrada:
            try:
                tab_btn = frame.locator(f'text="{tab}"').first
                await tab_btn.click(timeout=5000)
                abas_tentadas += 1
                log(f"  Aba '{tab}' clicada, buscando tarefa...", config.nome)
                await asyncio.sleep(3)

                if nome_tarefa and await buscar_tarefa_no_frame(frame, nome_tarefa, disciplina, agent):
                    await asyncio.sleep(4)
                    log(f"  Tarefa encontrada em {tab}!", config.nome)
                    tarefa_encontrada = True
                    break
                else:
                    log(f"  Tarefa nao encontrada na aba '{tab}'", config.nome)
            except Exception as e:
                log(f"  Erro na aba '{tab}': {str(e)[:50]}", config.nome)

    # Se nenhuma aba foi clicada com sucesso, tenta buscar direto com Vision
    if not tarefa_encontrada and abas_tentadas == 0 and agent:
        log("Nenhuma aba encontrada, tentando Vision direto...", config.nome)
        nome_curto = " ".join(nome_tarefa.split()[:5])
        try:
            encontrou = await agent._clicar_com_visao(
                f"Tarefa ou assignment com nome '{nome_curto}' na lista de tarefas do Teams"
            )
            if encontrou:
                await asyncio.sleep(4)
                log("  Tarefa encontrada via Vision!", config.nome)
                tarefa_encontrada = True
        except Exception as e:
            log(f"  Vision falhou: {e}", config.nome)

    if not tarefa_encontrada:
        log(f"Tarefa nao encontrada: {nome_tarefa}", config.nome)
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
            pdf_abriu = False

            # Tenta CSS primeiro
            try:
                pdf_link = frame.locator('text=/.pdf/i').first
                await pdf_link.click(timeout=5000)
                await asyncio.sleep(3)
                pdf_abriu = True
            except Exception:
                log("  CSS falhou para PDF, tentando Vision...", config.nome)

            # Fallback: Vision para clicar no PDF
            if not pdf_abriu and agent:
                pdf_abriu = await agent._clicar_com_visao(
                    "Arquivo PDF na secao 'Reference materials' ou 'Materiais de referencia'. Clique no nome do arquivo PDF."
                )
                if pdf_abriu:
                    await asyncio.sleep(3)

            if not pdf_abriu:
                log("  Nao conseguiu abrir o PDF", config.nome)
                raise Exception("PDF nao abriu")

            # Espera o preview carregar completamente
            log("  Aguardando preview carregar...", config.nome)

            try:
                await browser.page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await asyncio.sleep(5)

            # NOVO: Tenta baixar o arquivo antes de tirar screenshots
            download_ok = False
            arquivo_baixado = await baixar_arquivo_do_teams(browser, agent, config, data_dir)

            if arquivo_baixado and arquivo_baixado.exists():
                log(f"  Download do PDF bem-sucedido: {arquivo_baixado.name}", config.nome)
                conteudo = extrair_conteudo_arquivo(arquivo_baixado)

                if conteudo and conteudo.get("texto", "").strip():
                    tarefa_info["texto_extraido"] = conteudo["texto"]
                    log(f"  Texto extraido: {len(conteudo['texto'])} chars, {conteudo.get('paginas', 0)} paginas", config.nome)

                    # Base64 do PDF para envio nativo ao Claude
                    if conteudo.get("base64_data"):
                        tarefa_info.setdefault("pdf_base64", []).append(conteudo["base64_data"])
                        log("  PDF base64 salvo para envio nativo ao Claude", config.nome)

                    tarefa_info.setdefault("arquivos_baixados", []).append(str(arquivo_baixado))
                    download_ok = True
                else:
                    log("  Download OK mas extracao de texto falhou, usando screenshots", config.nome)

            if download_ok:
                # Download e extracao OK, fecha preview
                await fechar_preview(browser)
                frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)
            else:
                # FALLBACK: screenshots (fluxo original)
                log("  Usando fallback de screenshots para PDF...", config.nome)

                # Espera adicional para garantir que o conteudo renderizou
                await asyncio.sleep(5)

                # Verifica se ainda tem loading spinner
                try:
                    loading = browser.page.locator('[class*="loading"], [class*="spinner"], [class*="progress"]').first
                    await loading.wait_for(state="hidden", timeout=10000)
                except Exception:
                    pass

                await asyncio.sleep(3)

                # Verifica com Vision se o PDF realmente abriu
                if agent:
                    screenshot = await browser.page.screenshot(type="png")
                    import base64
                    img_base64 = base64.b64encode(screenshot).decode()

                    try:
                        from anthropic import Anthropic
                        client = Anthropic(api_key=config.anthropic_key)
                        response = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=100,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64}},
                                    {"type": "text", "text": "O conteudo de um PDF esta visivel nesta tela? Responda apenas YES ou NO."}
                                ]
                            }]
                        )
                        pdf_visivel = "YES" in response.content[0].text.upper()
                        log(f"  Vision verificou PDF visivel: {pdf_visivel}", config.nome)

                        if not pdf_visivel:
                            log("  PDF nao esta visivel, tentando clicar novamente...", config.nome)
                            clicou = await agent._clicar_com_visao(
                                "Arquivo PDF na lista de materiais de referencia. Clique no nome do arquivo PDF para abrir."
                            )
                            if clicou:
                                await asyncio.sleep(10)
                                screenshot2 = await browser.page.screenshot(type="png")
                                img_base64_2 = base64.b64encode(screenshot2).decode()
                                response2 = client.messages.create(
                                    model="claude-sonnet-4-20250514",
                                    max_tokens=100,
                                    messages=[{
                                        "role": "user",
                                        "content": [
                                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64_2}},
                                            {"type": "text", "text": "O conteudo de um PDF esta visivel nesta tela? Responda apenas YES ou NO."}
                                        ]
                                    }]
                                )
                                pdf_visivel = "YES" in response2.content[0].text.upper()
                                log(f"  Segunda verificacao: PDF visivel = {pdf_visivel}", config.nome)

                            if not pdf_visivel:
                                log("  PDF nao abriu, pulando tarefa para tentar novamente depois", config.nome)
                                resultado["status"] = "skipped"
                                resultado["error"] = "PDF nao abriu para leitura"
                                return resultado
                    except Exception as e:
                        if "PDF nao abriu" in str(e):
                            raise
                        log(f"  Erro na verificacao Vision: {e}", config.nome)

                ultimo_hash = None
                for page_num in range(1, MAX_PDF_PAGES + 1):
                    ss_path = data_dir / f"pdf_novo_{page_num}.png"
                    await browser.page.screenshot(path=str(ss_path))

                    with open(ss_path, "rb") as f:
                        current_hash = hashlib.md5(f.read()).hexdigest()

                    if current_hash == ultimo_hash:
                        log(f"  Pagina {page_num} igual a anterior, fim do PDF", config.nome)
                        ss_path.unlink()
                        break

                    ultimo_hash = current_hash
                    tarefa_info["screenshots"].append(str(ss_path))
                    log(f"  Screenshot {page_num} do PDF capturado", config.nome)

                    try:
                        for _ in range(15):
                            await browser.page.keyboard.press("ArrowDown")
                            await asyncio.sleep(0.1)
                        await browser.page.mouse.wheel(0, 500)
                        await asyncio.sleep(1)
                    except Exception:
                        break

                await fechar_preview(browser)
                frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)
        except Exception as e:
            log(f"  Erro ao processar PDF: {e}", config.nome)
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

    # Processa documentos anexados (DOCX, XLSX, PPTX)
    tem_docx_anexo = any(ext in content_lower for ext in [".docx", ".doc"])
    tem_xlsx_anexo = any(ext in content_lower for ext in [".xlsx", ".xls"])
    tem_pptx_anexo = any(ext in content_lower for ext in [".pptx", ".ppt"])

    if tem_docx_anexo or tem_xlsx_anexo or tem_pptx_anexo:
        log("Documento(s) anexado(s), processando...", config.nome)
        doc_extensions = []
        if tem_docx_anexo:
            doc_extensions.append(".docx")
        if tem_xlsx_anexo:
            doc_extensions.append(".xlsx")
        if tem_pptx_anexo:
            doc_extensions.append(".pptx")

        for ext in doc_extensions:
            if ext not in content_lower:
                continue
            try:
                # Encontra e clica no documento para abrir preview
                doc_link = frame.locator(f'text=/{re.escape(ext)}/i').first
                await doc_link.click(timeout=10000)
                await asyncio.sleep(5)

                # Tenta baixar o arquivo
                download_ok = False
                arquivo_baixado = await baixar_arquivo_do_teams(browser, agent, config, data_dir)

                if arquivo_baixado and arquivo_baixado.exists():
                    log(f"  Download de {ext} bem-sucedido: {arquivo_baixado.name}", config.nome)
                    conteudo = extrair_conteudo_arquivo(arquivo_baixado)

                    if conteudo and conteudo.get("texto", "").strip():
                        # Acumula texto extraido
                        texto_anterior = tarefa_info.get("texto_extraido", "")
                        separador = "\n\n" if texto_anterior else ""
                        tarefa_info["texto_extraido"] = texto_anterior + separador + conteudo["texto"]
                        log(f"  Texto extraido de {ext}: {len(conteudo['texto'])} chars", config.nome)

                        tarefa_info.setdefault("arquivos_baixados", []).append(str(arquivo_baixado))
                        download_ok = True
                    else:
                        log(f"  Download OK mas extracao falhou para {ext}, usando screenshots", config.nome)

                if download_ok:
                    await fechar_preview(browser)
                    frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)
                else:
                    # FALLBACK: screenshots (fluxo original)
                    log(f"  Usando fallback de screenshots para {ext}...", config.nome)
                    await asyncio.sleep(5)  # Espera preview carregar

                    max_doc_pages = 10
                    ultimo_hash = None
                    for page_num in range(1, max_doc_pages + 1):
                        ss_path = data_dir / f"doc_{ext.replace('.', '')}_{page_num}.png"
                        await browser.page.screenshot(path=str(ss_path))

                        with open(ss_path, "rb") as f:
                            current_hash = hashlib.md5(f.read()).hexdigest()

                        if current_hash == ultimo_hash:
                            log(f"  Pagina {page_num} igual a anterior, fim do documento", config.nome)
                            ss_path.unlink()
                            break

                        ultimo_hash = current_hash
                        tarefa_info["screenshots"].append(str(ss_path))
                        log(f"  Screenshot {page_num} do documento capturado", config.nome)

                        try:
                            for _ in range(15):
                                await browser.page.keyboard.press("ArrowDown")
                                await asyncio.sleep(0.1)
                            await browser.page.mouse.wheel(0, 500)
                            await asyncio.sleep(1)
                        except Exception:
                            break

                    await fechar_preview(browser)
                    frame = await recuperar_frame_tarefa(browser, frame, nome_tarefa, disciplina, agent)

            except Exception as e:
                log(f"  Erro ao processar documento {ext}: {e}", config.nome)
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
                disciplina=disciplina,
                instrucoes=tarefa_info.get("instrucoes", "")
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

    # Analisa intencao da tarefa antes de resolver
    log("Analisando intencao da tarefa...", config.nome)
    analise = analisar_intencao_tarefa(tarefa_info, config.anthropic_key)

    log(f"  Categoria: {analise['categoria']} ({analise['confianca']}%)", config.nome)
    log(f"  Motivo: {analise['motivo']}", config.nome)

    # Se nao pode resolver, pula a tarefa
    if not analise["pode_resolver"]:
        log(f"Tarefa nao resolvivel: {analise['categoria']}", config.nome)
        resultado["status"] = analise["status_skip"] or "skipped"
        resultado["error"] = f"{analise['categoria']}: {analise['motivo']}"
        resultado["instrucoes"] = tarefa_info.get("instrucoes", "")
        return resultado

    # Flag para revisao se confianca baixa ou incerto
    flag_revisar = analise.get("flag_revisar", False)
    if flag_revisar:
        log("  ⚠️ Tarefa marcada para revisao (confianca baixa)", config.nome)

    # Flag para anexar apenas (não enviar automaticamente)
    anexar_apenas = analise.get("anexar_apenas", False)
    if anexar_apenas:
        log("  📎 Tarefa será resolvida mas NÃO enviada (requer envio manual)", config.nome)

    # Resolve com Claude
    log("Enviando para Claude...", config.nome)
    resposta = resolver_com_claude(tarefa_info, config.anthropic_key, config.nome)

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
    if formato == "android":
        arquivos = criar_projeto_android(resposta, nome_tarefa, data_dir)
    elif formato == "zip":
        arquivos = extrair_projeto_multi_arquivo(resposta, nome_tarefa, data_dir)
    elif formato in ["html", "kotlin"] + FORMATOS_CODIGO:
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

    # Submit (apenas se não for anexar_apenas)
    if anexar_apenas:
        # Não clica em entregar - apenas anexa
        log("Arquivo(s) anexado(s) - aguardando envio manual pelo aluno", config.nome)

        # Screenshot de comprovacao
        comp_name = re.sub(r'[^\w]', '', nome_tarefa)[:30]
        comp_path = str(data_dir / f"anexado_{comp_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        await browser.page.screenshot(path=comp_path)

        # Notificacao por email (informando que precisa envio manual)
        if config.smtp_email and config.notification_email:
            try:
                notifier = EmailNotifier(
                    smtp_email=config.smtp_email,
                    smtp_password=config.smtp_password,
                    to_email=config.notification_email,
                )
                notifier.notify_tarefa_resolvida(
                    nome_tarefa, disciplina,
                    f"[ATENÇÃO: Envio manual necessário]\n\nA tarefa foi resolvida e o arquivo anexado, "
                    f"mas requer envio manual (ex: via repositório GitHub).\n\n{resposta[:500]}"
                )
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
        resultado["status"] = "ready_manual"
        resultado["format"] = formato
        resultado["instrucoes"] = tarefa_info.get("instrucoes", "")
        resultado["resposta"] = resposta
        resultado["arquivos"] = arquivos
        resultado["categoria"] = analise.get("categoria", "")
        resultado["confianca"] = analise.get("confianca", 0)
        limpar_downloads(data_dir)
        return resultado

    # Submit normal
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
        resultado["status"] = "success_flagged" if flag_revisar else "success"
        resultado["format"] = formato
        resultado["instrucoes"] = tarefa_info.get("instrucoes", "")
        resultado["resposta"] = resposta
        resultado["arquivos"] = arquivos
        resultado["categoria"] = analise.get("categoria", "")
        resultado["confianca"] = analise.get("confianca", 0)
        limpar_downloads(data_dir)
        return resultado

    except Exception as e:
        log(f"Erro ao enviar: {e}", config.nome)
        resultado["status"] = "error"
        resultado["format"] = formato
        resultado["error"] = str(e)
        resultado["instrucoes"] = tarefa_info.get("instrucoes", "")
        resultado["resposta"] = resposta if 'resposta' in dir() else ""
        resultado["arquivos"] = arquivos if 'arquivos' in dir() else []
        limpar_downloads(data_dir)
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

            # Contador de tarefas processadas neste ciclo
            tarefas_processadas_ciclo = 0

            for atividade in novas:
                # Verifica limite antes de processar cada atividade
                if config.limite_tarefas is not None:
                    tarefas_total = config.tarefas_mes + tarefas_processadas_ciclo
                    if tarefas_total >= config.limite_tarefas:
                        log(f"Limite de tarefas atingido ({tarefas_total}/{config.limite_tarefas}), parando ciclo", config.nome)
                        update_client_status(config.client_id, "idle", f"Limite atingido: {tarefas_total}/{config.limite_tarefas}")
                        break

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

                        # Atividades "atualizada" sao mais propensas a falso-positivo (posts, updates ja entregues)
                        max_tentativas = 1 if atividade.get("acao") == "atualizada" else MAX_TENTATIVAS_NOT_FOUND

                        if tentativas >= max_tentativas:
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
                            log(f"Atividade nao encontrada (tentativa {tentativas}/{max_tentativas}), vai tentar novamente", config.nome)

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
                        "instrucoes": res.get("instrucoes", ""),
                        "resposta": res.get("resposta", ""),
                        "arquivos": res.get("arquivos", []),
                    }
                    resultado["tasks"].append(task_result)

                    if res["status"] == "success":
                        resultado["success"] += 1
                        tarefas_processadas_ciclo += 1  # Conta para o limite
                    elif res["status"] == "error":
                        resultado["error"] += 1
                    # skipped, not_found, group não contam como erro nem para o limite

                except Exception as e:
                    log(f"Erro ao processar: {e}", config.nome)
                    resultado["tasks"].append({
                        "name": atividade.get("nome", ""),
                        "discipline": atividade.get("disciplina", ""),
                        "status": "error",
                        "format": "",
                        "error": str(e),
                        "instrucoes": "",
                        "resposta": "",
                        "arquivos": [],
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
