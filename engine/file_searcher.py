"""
FileSearcher - Agente para buscar arquivos em turmas do Teams.

Quando uma tarefa referencia um arquivo externo (ex: "veja o arquivo ADS1241-Aula03"),
este modulo navega ate a turma, encontra o arquivo e extrai seu conteudo.
"""

import re
import asyncio
from pathlib import Path
from typing import Optional
from loguru import logger


# Padroes para detectar referencias a arquivos externos nas instrucoes
PADROES_ARQUIVO_EXTERNO = [
    # "disponivel no arquivo X"
    r"dispon[ií]vel\s+(?:no|em)\s+(?:arquivo|material|documento)\s+([A-Za-z0-9_\-\.]+)",
    # "veja o arquivo X"
    r"veja\s+(?:o\s+)?(?:arquivo|material|documento)\s+([A-Za-z0-9_\-\.]+)",
    # "conforme arquivo X"
    r"conforme\s+(?:o\s+)?(?:arquivo|material|documento)\s+([A-Za-z0-9_\-\.]+)",
    # "no arquivo X"
    r"(?:no|em)\s+arquivo\s+([A-Za-z0-9_\-\.]+)",
    # "arquivo X.pdf" ou similar
    r"arquivo\s+([A-Za-z0-9_\-]+\.(?:pdf|docx|pptx|xlsx))",
    # Padrao especifico: SIGLA + Aula + Numero (ex: ADS1241-Aula03)
    r"([A-Z]{2,}\d+[-_]?[Aa]ula\d+)",
    # "Aula 03" ou "Aula03"
    r"(?:arquivo|material)\s+(?:da\s+)?[Aa]ula\s*(\d+)",
    # "material da aula X"
    r"material\s+da\s+aula\s*(\d+)",
]


def detectar_arquivo_externo(instrucoes: str) -> Optional[str]:
    """
    Detecta se as instrucoes referenciam um arquivo externo.

    Args:
        instrucoes: Texto das instrucoes da tarefa

    Returns:
        Nome do arquivo referenciado ou None

    Exemplos:
        "A definicao esta disponivel no arquivo ADS1241-Aula03" -> "ADS1241-Aula03"
        "Veja o arquivo trabalho.pdf" -> "trabalho.pdf"
        "Conforme material da Aula 5" -> "5" (sera buscado como Aula5)
    """
    if not instrucoes:
        return None

    for padrao in PADROES_ARQUIVO_EXTERNO:
        match = re.search(padrao, instrucoes, re.IGNORECASE)
        if match:
            arquivo = match.group(1).strip()
            # Remove pontuacao final se houver
            arquivo = arquivo.rstrip(".,;:")
            logger.info(f"Arquivo externo detectado: '{arquivo}' (padrao: {padrao[:30]}...)")
            return arquivo

    return None


def normalizar_nome_arquivo(nome: str) -> list[str]:
    """
    Gera variacoes do nome do arquivo para busca.

    Args:
        nome: Nome do arquivo detectado

    Returns:
        Lista de variacoes para tentar na busca

    Exemplo:
        "ADS1241-Aula03" -> ["ADS1241-Aula03", "ADS1241_Aula03", "Aula03", "Aula 03", "aula03"]
    """
    variacoes = [nome]

    # Versao lowercase
    variacoes.append(nome.lower())

    # Troca - por _
    if "-" in nome:
        variacoes.append(nome.replace("-", "_"))
        variacoes.append(nome.replace("-", " "))

    # Se tem padrao SIGLA-Aula, extrai so a parte da Aula
    match = re.search(r"[Aa]ula\s*(\d+)", nome)
    if match:
        num = match.group(1)
        variacoes.extend([
            f"Aula{num}",
            f"Aula {num}",
            f"aula{num}",
            f"Aula0{num}" if len(num) == 1 else f"Aula{num}",
        ])

    # Remove duplicatas mantendo ordem
    seen = set()
    return [x for x in variacoes if not (x in seen or seen.add(x))]


class FileSearcher:
    """Agente para buscar arquivos em turmas do Teams."""

    def __init__(self, browser, agent, data_dir: Path):
        """
        Inicializa o buscador.

        Args:
            browser: Instancia do TeamsBot
            agent: Instancia do TeamsAgent (para cliques resilientes)
            data_dir: Diretorio para salvar screenshots
        """
        self.browser = browser
        self.agent = agent
        self.data_dir = data_dir
        self.page = browser.page

    async def buscar_arquivo(
        self,
        nome_arquivo: str,
        disciplina: str
    ) -> dict:
        """
        Busca arquivo na turma e retorna conteudo.

        Args:
            nome_arquivo: Nome do arquivo a buscar
            disciplina: Nome da disciplina/turma

        Returns:
            {
                "encontrado": True/False,
                "conteudo": "texto extraido...",
                "screenshots": ["path1.png", "path2.png"],
                "tipo": "pdf" | "docx" | "pptx" | None,
                "erro": "mensagem de erro" (se houver)
            }
        """
        logger.info(f"Buscando arquivo '{nome_arquivo}' na turma '{disciplina}'")

        resultado = {
            "encontrado": False,
            "conteudo": "",
            "screenshots": [],
            "tipo": None,
            "erro": None
        }

        try:
            # 1. Navegar ate Teams/Turmas
            if not await self._ir_para_teams():
                resultado["erro"] = "Falha ao navegar para Teams"
                return resultado

            # 2. Encontrar e clicar na turma certa
            if not await self._entrar_na_turma(disciplina):
                resultado["erro"] = f"Turma nao encontrada: {disciplina}"
                return resultado

            # 3. Ir para aba Shared
            if not await self._ir_para_shared():
                resultado["erro"] = "Aba Shared nao encontrada"
                return resultado

            # 4. Buscar o arquivo
            arquivo_encontrado = await self._buscar_arquivo(nome_arquivo)

            if not arquivo_encontrado:
                resultado["erro"] = f"Arquivo nao encontrado: {nome_arquivo}"
                return resultado

            # 5. Abrir e extrair conteudo
            conteudo = await self._extrair_conteudo()
            resultado.update(conteudo)
            resultado["encontrado"] = True

        except Exception as e:
            logger.error(f"Erro ao buscar arquivo: {e}")
            resultado["erro"] = str(e)

        return resultado

    async def _ir_para_teams(self) -> bool:
        """Navega para a lista de turmas/Teams."""
        logger.info("Navegando para Teams...")

        # Tenta clicar no botao Teams
        clicked = await self.agent.clicar("teams")
        if clicked:
            await asyncio.sleep(3)
            return True

        # Fallback: tenta via URL ou outros metodos
        logger.warning("Botao Teams nao encontrado")
        return False

    async def _entrar_na_turma(self, disciplina: str) -> bool:
        """Encontra e entra na turma pela disciplina."""
        logger.info(f"Procurando turma: {disciplina}")

        await asyncio.sleep(2)

        # Extrai palavras-chave da disciplina
        # Ex: "2026.1-ADS1241/C02 - DESENVOLVIMENTO DE SOFTWARE WEB"
        # Busca por: "SOFTWARE WEB" ou "ADS1241"
        palavras = []

        # Pega codigo da disciplina (ex: ADS1241)
        match = re.search(r"([A-Z]{2,}\d+)", disciplina)
        if match:
            palavras.append(match.group(1))

        # Pega nome da disciplina apos o "-"
        if " - " in disciplina:
            nome = disciplina.split(" - ")[-1].strip()
            # Pega as ultimas 2-3 palavras mais significativas
            partes = nome.split()
            if len(partes) >= 2:
                palavras.append(" ".join(partes[-2:]))

        # Tenta encontrar a turma
        for palavra in palavras:
            try:
                logger.debug(f"Buscando turma com: {palavra}")
                turma = self.page.locator(f'text=/{re.escape(palavra)}/i').first
                await turma.click(timeout=5000)
                await asyncio.sleep(3)
                logger.info(f"Turma encontrada: {palavra}")
                return True
            except Exception:
                continue

        return False

    async def _ir_para_shared(self) -> bool:
        """Clica na aba Shared para acessar arquivos da turma."""
        logger.info("Navegando para aba Shared...")

        # Tenta clicar em "Shared" via CSS
        try:
            shared = self.page.locator('text=/^Shared$/i, [aria-label*="Shared"], button:has-text("Shared")').first
            await shared.click(timeout=5000)
            await asyncio.sleep(5)  # Espera 5 segundos apos clicar em Shared
            logger.info("Entrou em Shared via CSS")
            return True
        except Exception:
            logger.debug("CSS falhou para Shared, tentando Vision...")

        # Fallback: usa Vision
        try:
            encontrou = await self.agent._clicar_com_visao(
                "Aba 'Shared' no topo da pagina da turma do Teams, ao lado de 'Posts'"
            )
            if encontrou:
                await asyncio.sleep(5)  # Espera 5 segundos apos clicar em Shared
                logger.info("Entrou em Shared via Vision")
                return True
        except Exception as e:
            logger.error(f"Vision falhou para Shared: {e}")

        return False

    async def _buscar_arquivo(self, nome: str, nivel: int = 0) -> bool:
        """
        Busca arquivo por nome usando Vision, navegando em pastas se necessario.

        Args:
            nome: Nome do arquivo
            nivel: Nivel de profundidade na busca (max 3)

        Returns:
            True se encontrou e clicou no arquivo
        """
        if nivel > 2:
            logger.warning("Nivel maximo de busca atingido")
            return False

        variacoes = normalizar_nome_arquivo(nome)
        logger.info(f"Buscando arquivo (nivel {nivel}): {variacoes[:3]}...")

        await asyncio.sleep(2)

        # Screenshot para debug
        await self.page.screenshot(
            path=str(self.data_dir / f"shared_search_{nivel}.png")
        )

        # 1. Primeiro tenta CSS para cada variacao (clique no texto abre)
        for variacao in variacoes:
            try:
                arquivo = self.page.locator(f'text=/{re.escape(variacao)}/i').first
                await arquivo.click(timeout=3000)
                logger.info(f"Clique em arquivo/pasta via CSS: {variacao}")
                logger.info("Aguardando 40 segundos para preview carregar...")
                await asyncio.sleep(40)
                # Assume que o arquivo abriu (URL pode nao mudar no Teams)
                logger.info("Arquivo aberto, pronto para extrair conteudo!")
                return True

            except Exception:
                continue

        # 2. Usa Vision pra encontrar o arquivo
        logger.info(f"CSS falhou, usando Vision para buscar '{nome}'...")
        nome_curto = variacoes[0] if variacoes else nome

        try:
            # Pede pro Vision encontrar o arquivo (clique no texto abre)
            encontrou = await self.agent._clicar_com_visao(
                f"Clique no TEXTO/NOME do arquivo '{nome_curto}' na lista de arquivos do Teams. "
                f"Nao clique no icone, clique exatamente em cima do texto do nome do arquivo."
            )
            if encontrou:
                logger.info(f"Vision encontrou e clicou em '{nome_curto}'")
                logger.info("Aguardando 40 segundos para preview carregar...")
                await asyncio.sleep(40)
                # Assume que o arquivo abriu (URL pode nao mudar no Teams)
                logger.info("Arquivo aberto, pronto para extrair conteudo!")
                return True
        except Exception as e:
            logger.debug(f"Vision nao encontrou arquivo: {e}")

        # 3. Se nao encontrou arquivo, tenta encontrar qualquer pasta
        if nivel == 0:
            logger.info("Arquivo nao encontrado, procurando pastas...")
            try:
                # Clique no texto da pasta abre
                encontrou_pasta = await self.agent._clicar_com_visao(
                    "Uma pasta ou diretorio na lista de arquivos do Teams. "
                    "Clique no TEXTO/NOME da pasta, nao no icone amarelo."
                )
                if encontrou_pasta:
                    logger.info("Clicou na pasta, aguardando 10 segundos para carregar...")
                    await asyncio.sleep(10)  # Espera 10 segundos apos abrir a pasta
                    logger.info("Pasta aberta, buscando arquivo dentro...")
                    return await self._buscar_arquivo(nome, nivel + 1)
            except Exception as e:
                logger.debug(f"Nenhuma pasta encontrada: {e}")

        return False

    async def _extrair_conteudo(self) -> dict:
        """
        Extrai conteudo do arquivo aberto.

        Returns:
            {
                "conteudo": "texto...",
                "screenshots": ["path1.png", ...],
                "tipo": "pdf" | "docx" | etc
            }
        """
        resultado = {
            "conteudo": "",
            "screenshots": [],
            "tipo": None
        }

        logger.info("Extraindo conteudo do arquivo...")
        await asyncio.sleep(3)

        # Screenshot do arquivo aberto
        ss_path = self.data_dir / "arquivo_externo_1.png"
        await self.page.screenshot(path=str(ss_path))
        resultado["screenshots"].append(str(ss_path))
        logger.info(f"Screenshot 1 salvo: {ss_path}")

        # Guarda bytes da ultima screenshot para comparar
        with open(ss_path, "rb") as f:
            ultima_screenshot = f.read()

        # Tenta extrair texto visivel
        try:
            # Pega texto do corpo da pagina/preview
            body_text = await self.page.inner_text("body", timeout=5000)

            # Limpa e limita o texto
            texto_limpo = body_text.strip()[:5000]
            resultado["conteudo"] = texto_limpo
            logger.info(f"Texto extraido: {len(texto_limpo)} caracteres")

        except Exception as e:
            logger.warning(f"Nao conseguiu extrair texto: {e}")

        # Faz scroll e captura mais paginas ate screenshot ser igual a anterior
        max_paginas = 30
        scrolls_por_pagina = 15  # Quantas setinhas pra baixo antes de cada print

        for i in range(2, max_paginas + 1):
            try:
                # Faz 15 setinhas pra baixo
                logger.info(f"Scrollando {scrolls_por_pagina}x para baixo...")
                for _ in range(scrolls_por_pagina):
                    await self.page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.1)

                await asyncio.sleep(2)  # Espera 2 segundos para carregar

                # Tira screenshot
                ss_path = self.data_dir / f"arquivo_externo_{i}.png"
                await self.page.screenshot(path=str(ss_path))

                # Compara com screenshot anterior
                with open(ss_path, "rb") as f:
                    screenshot_atual = f.read()

                if screenshot_atual == ultima_screenshot:
                    logger.info(f"Screenshot {i} igual a anterior - fim do documento")
                    # Remove screenshot duplicado
                    import os
                    os.remove(ss_path)
                    break

                resultado["screenshots"].append(str(ss_path))
                logger.info(f"Screenshot {i} salvo: {ss_path}")
                ultima_screenshot = screenshot_atual

            except Exception as e:
                logger.warning(f"Erro ao capturar screenshot {i}: {e}")
                break

        logger.info(f"Total: {len(resultado['screenshots'])} screenshots capturados")
        return resultado
