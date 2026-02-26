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

            # 3. Ir para aba Files
            if not await self._ir_para_files():
                resultado["erro"] = "Aba Files nao encontrada"
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

    async def _ir_para_files(self) -> bool:
        """Clica na aba Files/Arquivos ou General/Shared."""
        logger.info("Navegando para aba Files...")

        # Primeiro tenta clicar em General (canal padrao)
        try:
            general = self.page.locator('text=/General|Geral/i').first
            await general.click(timeout=5000)
            await asyncio.sleep(2)
            logger.info("Entrou no canal General")
        except Exception:
            logger.debug("Canal General nao encontrado, continuando...")

        # Tenta clicar na aba Files
        clicked = await self.agent.clicar("files")
        if clicked:
            await asyncio.sleep(3)
            return True

        # Fallback: tenta clicar em "Shared" diretamente
        try:
            shared = self.page.locator('text=/Shared|Compartilhado/i').first
            await shared.click(timeout=5000)
            await asyncio.sleep(3)
            logger.info("Entrou em Shared")
            return True
        except Exception:
            pass

        return False

    async def _buscar_arquivo(self, nome: str, nivel: int = 0) -> bool:
        """
        Busca arquivo por nome, navegando em pastas se necessario.

        Args:
            nome: Nome do arquivo
            nivel: Nivel de profundidade na busca (max 3)

        Returns:
            True se encontrou e clicou no arquivo
        """
        if nivel > 3:
            logger.warning("Nivel maximo de busca atingido")
            return False

        variacoes = normalizar_nome_arquivo(nome)
        logger.info(f"Buscando arquivo (nivel {nivel}): {variacoes[:3]}...")

        await asyncio.sleep(2)

        # Screenshot para debug
        await self.page.screenshot(
            path=str(self.data_dir / f"files_search_{nivel}.png")
        )

        # Tenta cada variacao
        for variacao in variacoes:
            try:
                # Busca elemento com o nome
                arquivo = self.page.locator(f'text=/{re.escape(variacao)}/i').first

                # Verifica se e pasta ou arquivo
                elemento_texto = await arquivo.inner_text(timeout=3000)

                # Clica no elemento
                await arquivo.click(timeout=5000)
                await asyncio.sleep(2)

                # Se parece ser pasta (nao tem extensao), faz busca recursiva
                if not any(ext in elemento_texto.lower() for ext in ['.pdf', '.docx', '.pptx', '.xlsx']):
                    logger.info(f"Entrou em pasta: {variacao}")
                    # Continua busca dentro da pasta
                    return await self._buscar_arquivo(nome, nivel + 1)

                logger.info(f"Arquivo encontrado: {variacao}")
                return True

            except Exception as e:
                logger.debug(f"Variacao '{variacao}' nao encontrada: {e}")
                continue

        # Se nao achou, tenta entrar em pastas visiveis
        if nivel == 0:
            try:
                # Procura por pastas comuns
                pastas_comuns = ["Material", "Materiais", "Aulas", "Arquivos", "Documents"]
                for pasta in pastas_comuns:
                    try:
                        pasta_elem = self.page.locator(f'text=/{pasta}/i').first
                        await pasta_elem.click(timeout=3000)
                        await asyncio.sleep(2)

                        if await self._buscar_arquivo(nome, nivel + 1):
                            return True

                        # Volta (clica em back ou breadcrumb)
                        await self.page.go_back()
                        await asyncio.sleep(2)
                    except Exception:
                        continue
            except Exception:
                pass

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

        await asyncio.sleep(3)

        # Screenshot do arquivo aberto
        ss_path = self.data_dir / "arquivo_externo_1.png"
        await self.page.screenshot(path=str(ss_path))
        resultado["screenshots"].append(str(ss_path))

        # Tenta extrair texto visivel
        try:
            # Pega texto do corpo da pagina/preview
            body_text = await self.page.inner_text("body", timeout=5000)

            # Limpa e limita o texto
            texto_limpo = body_text.strip()[:5000]
            resultado["conteudo"] = texto_limpo

        except Exception as e:
            logger.warning(f"Nao conseguiu extrair texto: {e}")

        # Tenta fazer scroll e capturar mais paginas (para PDFs)
        for i in range(2, 6):  # Ate 5 paginas
            try:
                # Scroll down
                await self.page.keyboard.press("PageDown")
                await asyncio.sleep(1)

                ss_path = self.data_dir / f"arquivo_externo_{i}.png"
                await self.page.screenshot(path=str(ss_path))
                resultado["screenshots"].append(str(ss_path))

            except Exception:
                break

        return resultado
