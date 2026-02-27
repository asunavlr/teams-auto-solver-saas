"""
TeamsAgent - Agente de navegacao inteligente com fallback.

Tenta seletores CSS primeiro (rapido, custo zero).
Se falhar, usa Claude Vision para identificar onde clicar (resiliente).
"""

import base64
import re
from typing import Optional, Tuple
from loguru import logger
from anthropic import Anthropic
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


class TeamsAgent:
    """Agente de navegacao com fallback inteligente CSS -> Claude Vision."""

    # Mapa de seletores CSS conhecidos (tentados primeiro)
    SELECTORS = {
        "atividade": [
            'button[data-tid="activity-button"]',
            '[data-tid="activity-button"]',
            'button[aria-label*="Activity"]',
            'button[aria-label*="Atividade"]',
            '[aria-label*="Activity"]',
            '[aria-label*="Atividade"]',
            'button:has-text("Activity")',
            'button:has-text("Atividade")',
            '[role="tab"]:has-text("Activity")',
            '[role="tab"]:has-text("Atividade")',
            'li:has-text("Activity") button',
            'li:has-text("Atividade") button',
        ],
        "tarefas": [
            'button[data-tid="assignments-button"]',
            '[aria-label*="Assignment"]',
            '[aria-label*="Tarefas"]',
            'button:has-text("Assignments")',
            'button:has-text("Tarefas")',
        ],
        "entregar": [
            'button:has-text("Turn in")',
            'button:has-text("Entregar")',
            'button:has-text("Submit")',
            '[data-tid="turn-in-button"]',
        ],
        "adicionar_trabalho": [
            'button:has-text("Add work")',
            'button:has-text("Adicionar trabalho")',
            'button:has-text("Attach")',
            '[data-tid="add-work-button"]',
        ],
        "confirmar": [
            'button:has-text("Turn in")',
            'button:has-text("Entregar")',
            'button:has-text("Yes")',
            'button:has-text("Sim")',
            'button:has-text("Confirm")',
            'button:has-text("Confirmar")',
        ],
        "fechar": [
            'button[aria-label="Close"]',
            'button[aria-label="Fechar"]',
            'button:has-text("Close")',
            'button:has-text("Fechar")',
            '[data-tid="close-button"]',
        ],
        "voltar": [
            'button[aria-label="Back"]',
            'button[aria-label="Voltar"]',
            'button:has-text("Back")',
            'button:has-text("Voltar")',
            '[data-tid="back-button"]',
        ],
        "teams": [
            'button[data-tid="teams-button"]',
            '[data-tid="teams-button"]',
            'button[aria-label*="Teams"]',
            'button[aria-label*="Equipes"]',
            '[aria-label*="Teams"]',
            '[aria-label*="Equipes"]',
            'button:has-text("Teams")',
            'button:has-text("Equipes")',
            '[role="tab"]:has-text("Teams")',
            '[role="tab"]:has-text("Equipes")',
            'li:has-text("Teams") button',
        ],
        "files": [
            'button[data-tid="files-tab"]',
            '[data-tid="files-tab"]',
            'button[aria-label*="Files"]',
            'button[aria-label*="Arquivos"]',
            '[aria-label*="Files"]',
            '[aria-label*="Arquivos"]',
            'button:has-text("Files")',
            'button:has-text("Arquivos")',
            '[role="tab"]:has-text("Files")',
            '[role="tab"]:has-text("Arquivos")',
            'a:has-text("Files")',
            'a:has-text("Arquivos")',
        ],
    }

    # Descricoes para o Claude quando CSS falha
    DESCRICOES = {
        "atividade": "Botao de Atividade ou Activity no menu lateral esquerdo do Teams",
        "tarefas": "Botao de Tarefas ou Assignments no menu lateral esquerdo do Teams",
        "entregar": "Botao azul de Entregar ou Turn in para submeter a tarefa",
        "adicionar_trabalho": "Botao de Adicionar trabalho ou Add work para anexar arquivo",
        "confirmar": "Botao de confirmacao (Turn in, Entregar, Yes, Sim) em um dialogo",
        "fechar": "Botao X ou Close para fechar modal/painel",
        "voltar": "Botao de voltar ou seta para esquerda",
        "teams": "Botao Teams ou Equipes no menu lateral esquerdo para ver lista de turmas",
        "files": "Aba Files ou Arquivos dentro de uma turma para ver materiais compartilhados",
    }

    def __init__(self, page: Page, anthropic_key: str):
        """
        Inicializa o agente.

        Args:
            page: Pagina do Playwright
            anthropic_key: Chave da API Anthropic
        """
        self.page = page
        self.client = Anthropic(api_key=anthropic_key)
        self.vision_calls = 0  # Contador de chamadas Vision (para metricas)

    async def clicar(self, objetivo: str, timeout: int = 5000) -> bool:
        """
        Clica em um elemento: tenta CSS primeiro, fallback para Vision.

        Args:
            objetivo: Chave do SELECTORS ou descricao livre
            timeout: Timeout em ms para tentativas CSS (default: 5000ms)

        Returns:
            True se clicou com sucesso, False caso contrario
        """
        import asyncio

        # Espera a pagina estabilizar (3 segundos)
        logger.info(f"Aguardando pagina carregar antes de clicar em '{objetivo}'...")
        await asyncio.sleep(3)

        # 1. Tenta seletores CSS conhecidos
        if objetivo in self.SELECTORS:
            logger.info(f"Tentando {len(self.SELECTORS[objetivo])} seletores CSS para '{objetivo}'")
            for i, selector in enumerate(self.SELECTORS[objetivo]):
                try:
                    logger.debug(f"  [{i+1}] Tentando: {selector}")
                    await self.page.click(selector, timeout=timeout)
                    logger.info(f"CSS funcionou para '{objetivo}': {selector}")
                    return True
                except PlaywrightTimeout:
                    logger.debug(f"  [{i+1}] Timeout: {selector}")
                    continue
                except Exception as e:
                    logger.debug(f"  [{i+1}] Erro: {selector} - {e}")
                    continue

        # 2. Fallback: Claude Vision
        descricao = self.DESCRICOES.get(objetivo, objetivo)
        logger.warning(f"Todos CSS falharam para '{objetivo}', usando Claude Vision")
        return await self._clicar_com_visao(descricao)

    async def _clicar_com_visao(self, descricao: str, duplo_clique: bool = False) -> bool:
        """
        Usa Claude Vision para identificar e clicar em elemento.

        Args:
            descricao: Descricao do que queremos clicar
            duplo_clique: Se True, faz duplo clique em vez de clique simples

        Returns:
            True se clicou, False se nao encontrou
        """
        self.vision_calls += 1

        # Screenshot da tela atual
        screenshot = await self.page.screenshot(type="png")
        img_base64 = base64.b64encode(screenshot).decode()

        # Pega dimensoes da viewport
        viewport = self.page.viewport_size
        width = viewport["width"] if viewport else 1280
        height = viewport["height"] if viewport else 720

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": f"""Analise esta tela do Microsoft Teams.
Dimensoes: {width}x{height} pixels

OBJETIVO: Encontrar e retornar as coordenadas para clicar em:
{descricao}

RESPONDA APENAS no formato:
CLICK: x, y

Onde x e y sao as coordenadas do CENTRO do botao/elemento.
Se nao encontrar o elemento, responda:
NOT_FOUND: motivo breve"""
                        }
                    ]
                }]
            )

            text = response.content[0].text.strip()
            logger.debug(f"Claude Vision resposta: {text}")

            # Procura CLICK: em qualquer lugar da resposta
            click_match = re.search(r"CLICK:\s*(\d+)\s*,\s*(\d+)", text)
            if click_match:
                x, y = int(click_match.group(1)), int(click_match.group(2))
                if duplo_clique:
                    logger.info(f"Claude Vision: duplo clique em ({x}, {y}) para '{descricao}'")
                    await self.page.mouse.dblclick(x, y)
                else:
                    logger.info(f"Claude Vision: clicando em ({x}, {y}) para '{descricao}'")
                    await self.page.mouse.click(x, y)
                await self.page.wait_for_timeout(1000)
                return True

            logger.warning(f"Claude Vision nao encontrou: {descricao} - {text}")
            return False

        except Exception as e:
            logger.error(f"Erro Claude Vision: {e}")
            return False

    async def digitar(self, texto: str) -> bool:
        """
        Digita texto no campo atualmente focado.

        Args:
            texto: Texto a digitar

        Returns:
            True se digitou
        """
        try:
            await self.page.keyboard.type(texto, delay=50)
            return True
        except Exception as e:
            logger.error(f"Erro ao digitar: {e}")
            return False

    async def scroll(self, direcao: str = "down", pixels: int = 300) -> bool:
        """
        Rola a pagina.

        Args:
            direcao: "up" ou "down"
            pixels: Quantidade de pixels

        Returns:
            True se rolou
        """
        try:
            delta = -pixels if direcao == "up" else pixels
            await self.page.mouse.wheel(0, delta)
            await self.page.wait_for_timeout(500)
            return True
        except Exception as e:
            logger.error(f"Erro ao rolar: {e}")
            return False

    async def esperar_elemento(self, objetivo: str, timeout: int = 10000) -> bool:
        """
        Espera um elemento aparecer.

        Args:
            objetivo: Chave do SELECTORS
            timeout: Timeout em ms

        Returns:
            True se elemento apareceu
        """
        if objetivo not in self.SELECTORS:
            return False

        for selector in self.SELECTORS[objetivo]:
            try:
                await self.page.wait_for_selector(selector, timeout=timeout)
                return True
            except:
                continue

        return False

    async def extrair_texto(self, objetivo: str) -> Optional[str]:
        """
        Extrai texto de um elemento.

        Args:
            objetivo: Chave do SELECTORS ou seletor CSS

        Returns:
            Texto do elemento ou None
        """
        selectors = self.SELECTORS.get(objetivo, [objetivo])

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    return await element.text_content()
            except:
                continue

        return None

    async def encontrar_e_clicar_texto(self, texto: str, timeout: int = 3000) -> bool:
        """
        Encontra elemento por texto visivel e clica.

        Args:
            texto: Texto a procurar
            timeout: Timeout em ms

        Returns:
            True se encontrou e clicou
        """
        selectors = [
            f'button:has-text("{texto}")',
            f'a:has-text("{texto}")',
            f'span:has-text("{texto}")',
            f'div:has-text("{texto}")',
            f'[role="button"]:has-text("{texto}")',
        ]

        for selector in selectors:
            try:
                await self.page.click(selector, timeout=timeout)
                logger.debug(f"Texto encontrado e clicado: {texto}")
                return True
            except:
                continue

        # Fallback Vision
        logger.warning(f"Texto '{texto}' nao encontrado via CSS, usando Vision")
        return await self._clicar_com_visao(f"Elemento com texto '{texto}'")

    async def screenshot_para_analise(self) -> str:
        """
        Tira screenshot e retorna como base64.

        Returns:
            Screenshot em base64
        """
        screenshot = await self.page.screenshot(type="png")
        return base64.b64encode(screenshot).decode()

    def get_stats(self) -> dict:
        """
        Retorna estatisticas de uso.

        Returns:
            Dict com metricas
        """
        return {
            "vision_calls": self.vision_calls,
            "estimated_cost": self.vision_calls * 0.08  # ~R$0.08 por chamada
        }
