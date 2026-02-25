"""
Modulo de automacao do navegador com Playwright.
Refatorado para suportar multiplos clientes.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from loguru import logger


class TeamsBrowser:
    """Gerencia a sessao do navegador no Teams para um cliente."""

    TEAMS_URL = "https://teams.microsoft.com"

    def __init__(self, auth_state_path: Path, teams_email: str, teams_password: str):
        self.auth_state_path = auth_state_path
        self.teams_email = teams_email
        self.teams_password = teams_password
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self, headless: bool = True):
        """Inicia o navegador."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )

        if self.auth_state_path.exists():
            logger.info("Carregando sessao salva...")
            self.context = await self.browser.new_context(
                storage_state=str(self.auth_state_path)
            )
        else:
            self.context = await self.browser.new_context()

        self.page = await self.context.new_page()
        logger.info("Navegador iniciado")

    async def login(self) -> bool:
        """Faz login no Teams."""
        if not self.page:
            raise RuntimeError("Navegador nao iniciado. Chame start() primeiro.")

        logger.info("Iniciando login no Teams...")
        await self.page.goto(self.TEAMS_URL)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(5)

        if await self._is_logged_in():
            logger.info("Ja esta logado!")
            return True

        try:
            email_input = self.page.locator('input[type="email"]')
            await email_input.wait_for(timeout=5000)
        except Exception:
            logger.info("Nao encontrou tela de login, assumindo ja logado")
            return True

        try:
            email_input = self.page.locator('input[type="email"]')
            await email_input.wait_for(timeout=10000)
            await email_input.fill(self.teams_email)
            await asyncio.sleep(1)

            # Espera botao Next ficar habilitado
            next_btn = self.page.locator('input[type="submit"]:not([disabled])')
            await next_btn.wait_for(state="visible", timeout=10000)
            await next_btn.click()

            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # Pagina de senha (pode ser da instituicao)
            password_input = self.page.locator('input[type="password"]')
            await password_input.wait_for(timeout=15000)
            await asyncio.sleep(1)
            await password_input.fill(self.teams_password)
            await asyncio.sleep(1)

            submit_btn = self.page.locator('input[type="submit"]:not([disabled]), button[type="submit"]').first
            await submit_btn.wait_for(state="visible", timeout=10000)
            await submit_btn.click()

            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            try:
                stay_signed = self.page.locator('text="Sim"').or_(
                    self.page.locator('text="Yes"')
                ).or_(
                    self.page.locator('input[value="Yes"]')
                )
                await stay_signed.click(timeout=5000)
            except Exception:
                pass

            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(5)

            if await self._is_logged_in():
                logger.info("Login realizado com sucesso!")
                await self._save_auth_state()
                return True
            else:
                logger.error("Falha no login")
                return False

        except Exception as e:
            logger.error(f"Erro durante login: {e}")
            return False

    async def _is_logged_in(self) -> bool:
        """Verifica se esta logado no Teams."""
        try:
            url = self.page.url
            if "login" in url or "oauth" in url:
                return False

            teams_app = self.page.locator('[data-tid="app-bar"]').or_(
                self.page.locator('[data-tid="teams-app-bar"]')
            ).or_(
                self.page.locator('[data-tid="activity-feed-btn"]')
            ).or_(
                self.page.locator('[data-tid="chat-tab"]')
            ).or_(
                self.page.locator('button[aria-label*="Chat"]')
            ).or_(
                self.page.locator('button[aria-label*="Equipes"]')
            ).or_(
                self.page.locator('button[aria-label*="Teams"]')
            )
            await teams_app.wait_for(timeout=8000)
            return True
        except Exception:
            return False

    async def _save_auth_state(self):
        """Salva o estado de autenticacao."""
        if self.context:
            self.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(self.auth_state_path))
            logger.info("Estado de autenticacao salvo")

    async def close(self):
        """Fecha o navegador."""
        if self.context:
            await self._save_auth_state()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Navegador fechado")
