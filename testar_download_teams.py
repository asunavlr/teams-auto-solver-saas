"""
Teste end-to-end do download de arquivos do Teams.
Puxa credenciais do banco de dados (Supabase) e roda com browser visivel.

Uso: python testar_download_teams.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger


async def testar_download():
    """Teste completo do fluxo de download usando dados do banco."""

    print("=" * 60)
    print("TESTE E2E - Download de Arquivos do Teams")
    print("=" * 60)

    # 1. Pegar credenciais do banco
    print("\n[1/8] Buscando clientes no banco...")

    from web import create_app, db
    from web.models import Client

    app = create_app()
    with app.app_context():
        clientes = Client.query.filter_by(status="active").all()

        if not clientes:
            clientes = Client.query.all()

        if not clientes:
            print("  NENHUM cliente cadastrado no banco!")
            print("  Cadastre um cliente pelo painel admin primeiro.")
            return

        print(f"  Encontrados {len(clientes)} cliente(s):")
        for i, c in enumerate(clientes):
            print(f"    [{i}] {c.nome} - {c.teams_email} (status: {c.status})")

        # Seleciona cliente (por argumento ou o primeiro)
        client_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
        if client_idx >= len(clientes):
            print(f"  Indice {client_idx} invalido!")
            return
        cliente = clientes[client_idx]
        print(f"\n  Usando: {cliente.nome} ({cliente.teams_email})")

        # Decripta credenciais
        teams_email = cliente.teams_email
        teams_password = cliente.teams_password
        anthropic_key = cliente.anthropic_key
        data_dir = cliente.data_dir

        print(f"  Teams email: {teams_email}")
        print(f"  Teams password: {'*' * len(teams_password) if teams_password else 'VAZIO!'}")
        print(f"  Anthropic key: {anthropic_key[:20]}..." if anthropic_key else "  Anthropic key: VAZIO!")
        print(f"  Data dir: {data_dir}")

    if not teams_email or not teams_password:
        print("\n  ERRO: Credenciais do Teams vazias!")
        return

    # 2. Iniciar browser (VISIVEL)
    print("\n[2/8] Iniciando browser (headless=false)...")
    from engine.browser import TeamsBrowser
    from engine.agent import TeamsAgent
    from engine.file_extractor import extrair_conteudo_arquivo

    auth_state = data_dir / "auth_state.json"
    browser = TeamsBrowser(auth_state, teams_email, teams_password)
    await browser.start(headless=False)
    print("  OK - Browser aberto com janela visivel")

    # Cria agente (se tiver API key)
    agent = None
    if anthropic_key:
        agent = TeamsAgent(browser.page, anthropic_key)
        print("  OK - Agente Vision disponivel")
    else:
        print("  AVISO - Sem API key, agente Vision indisponivel (so CSS)")

    try:
        # 3. Login no Teams
        print("\n[3/8] Fazendo login no Teams...")
        logado = await browser.login()
        if not logado:
            print("  FALHOU - Login falhou")
            return
        print("  OK - Logado no Teams")

        # 4. Navegar para Activity
        print("\n[4/8] Navegando para Activity...")
        await asyncio.sleep(3)

        if agent:
            clicou = await agent.clicar("atividade")
        else:
            clicou = False
            for sel in TeamsAgent.SELECTORS["atividade"]:
                try:
                    await browser.page.click(sel, timeout=3000)
                    clicou = True
                    break
                except Exception:
                    continue

        if clicou:
            print("  OK - Navegou para Activity")
        else:
            print("  AVISO - Nao conseguiu clicar, pode ja estar na tela")

        await asyncio.sleep(5)

        # 5. Procurar tarefa com anexo no feed
        print("\n[5/8] Procurando tarefa com anexo no feed...")
        await asyncio.sleep(3)

        body_text = ""
        try:
            body_text = await browser.page.inner_text("body", timeout=5000)
        except Exception:
            pass

        extensoes = [".pdf", ".docx", ".xlsx", ".pptx"]
        encontrou = None
        for ext in extensoes:
            if ext in body_text.lower():
                encontrou = ext
                break

        if encontrou:
            print(f"  OK - Referencia a '{encontrou}' encontrada!")
        else:
            print("  Nenhum anexo visivel no feed, procurando tarefa qualquer...")

        # Navega pelo feed: scroll down e tenta cada tarefa
        tem_anexo = False
        tipo_anexo = None
        frame = browser.page
        max_tentativas_tarefas = 8

        # Clica na primeira tarefa do feed (top) pra comecar
        for tentativa in range(max_tentativas_tarefas):
            print(f"\n  Tentativa {tentativa + 1}/{max_tentativas_tarefas}...")

            # Scroll no feed pra mostrar mais tarefas
            if tentativa > 0:
                try:
                    # Clica em Back pra voltar ao feed
                    back_btn = browser.page.locator('button[aria-label*="Back"], button[aria-label*="Voltar"]').first
                    await back_btn.click(timeout=3000)
                    await asyncio.sleep(2)
                except Exception:
                    await browser.page.keyboard.press("Escape")
                    await asyncio.sleep(2)

                # Scroll no feed pra baixo
                try:
                    feed_area = browser.page.locator('[aria-label*="Activity"], [class*="activity"]').first
                    for _ in range(tentativa * 3):
                        await browser.page.mouse.wheel(0, 200)
                        await asyncio.sleep(0.2)
                except Exception:
                    pass
                await asyncio.sleep(1)

            # Pede ao Vision pra clicar em tarefa
            if agent:
                if tentativa == 0:
                    desc = "A PRIMEIRA notificacao no feed de atividades do Teams (a mais no topo da lista)"
                elif tentativa <= 3:
                    desc = f"A notificacao #{tentativa + 1} de cima pra baixo no feed de atividades do Teams (a que AINDA NAO foi clicada)"
                else:
                    desc = f"Qualquer notificacao no feed de atividades que ainda nao tenha sido aberta. Procure uma diferente das anteriores, mais pra baixo na lista."
                clicou_tarefa = await agent._clicar_com_visao(desc)
            else:
                clicou_tarefa = False

            if not clicou_tarefa:
                print(f"    Nao conseguiu clicar")
                continue

            await asyncio.sleep(5)

            # Procura nos frames
            frame = browser.page
            for f in browser.page.frames:
                if "assignments" in f.url.lower():
                    frame = f
                    break

            frame_text = ""
            try:
                frame_text = await frame.inner_text("body", timeout=5000)
            except Exception:
                pass

            for ext in extensoes:
                if ext in frame_text.lower():
                    tem_anexo = True
                    tipo_anexo = ext
                    break

            if tem_anexo:
                print(f"    ACHOU! Tarefa com anexo {tipo_anexo}")
                break
            else:
                # Mostra nome da tarefa pra debug
                nome = ""
                try:
                    nome = frame_text.split("\n")[0][:60] if frame_text else "?"
                except Exception:
                    pass
                print(f"    Sem anexo: {nome}...")

        # 6. Se entrou numa tarefa com anexo
        print(f"\n[6/8] {'Anexo encontrado: ' + tipo_anexo if tem_anexo else 'Nenhum anexo encontrado'}...")

        if tem_anexo:
            print(f"  OK - Anexo {tipo_anexo} encontrado na tarefa!")
            print(f"  Tentando abrir preview do {tipo_anexo}...")

            # Clica no anexo
            try:
                import re
                link = frame.locator(f'text=/{re.escape(tipo_anexo)}/i').first
                await link.click(timeout=10000)
                print(f"  OK - Clicou no link do {tipo_anexo}")
                await asyncio.sleep(8)
            except Exception as e:
                print(f"  CSS falhou: {e}")
                if agent:
                    print("  Tentando Vision...")
                    await agent._clicar_com_visao(
                        f"Arquivo {tipo_anexo} na secao de materiais de referencia"
                    )
                    await asyncio.sleep(8)

            # 7. TENTA DOWNLOAD (usando baixar_arquivo_do_teams do monitor)
            print("\n[7/8] TESTANDO DOWNLOAD DO ARQUIVO...")
            from engine.monitor import baixar_arquivo_do_teams, limpar_downloads

            # Cria um config fake pro teste
            class FakeConfig:
                def __init__(self, nome):
                    self.nome = nome
                    self.anthropic_key = anthropic_key

            fake_config = FakeConfig(cliente.nome)

            downloads_dir = data_dir / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)

            download_ok = False
            filepath_baixado = None

            filepath_baixado = await baixar_arquivo_do_teams(browser, agent, fake_config, data_dir)
            if filepath_baixado and filepath_baixado.exists():
                download_ok = True
                print(f"  SUCESSO! Arquivo: {filepath_baixado.name} ({filepath_baixado.stat().st_size} bytes)")

            # 8. Extrai texto do arquivo baixado
            print("\n[8/8] Extraindo texto do arquivo...")
            if download_ok and filepath_baixado and filepath_baixado.exists():
                resultado = extrair_conteudo_arquivo(filepath_baixado)
                if resultado:
                    texto = resultado.get("texto", "")
                    paginas = resultado.get("paginas", 0)
                    base64_data = resultado.get("base64_data")
                    print(f"  Texto: {len(texto)} caracteres")
                    print(f"  Paginas: {paginas}")
                    print(f"  Base64: {'Sim (' + str(len(base64_data)) + ' chars)' if base64_data else 'N/A'}")
                    print(f"\n  === PREVIEW DO TEXTO ===")
                    print(f"  {texto[:500]}")
                    if len(texto) > 500:
                        print(f"  ... (+{len(texto) - 500} chars)")
                else:
                    print(f"  Formato nao suportado para extracao")
            else:
                print("  Nenhum arquivo foi baixado para extrair")

        else:
            print("  Nenhum anexo encontrado nesta tarefa")
            print("\n[7/8] PULADO - sem anexo")
            print("[8/8] PULADO - sem download")

        # Screenshot final
        ss_path = data_dir / "teste_download_final.png"
        await browser.page.screenshot(path=str(ss_path))
        print(f"\nScreenshot final: {ss_path}")

        print("\n" + "=" * 60)
        print("RESULTADO:")
        if tem_anexo and download_ok:
            print("  DOWNLOAD FUNCIONOU!")
        elif tem_anexo and not download_ok:
            print("  DOWNLOAD FALHOU - precisa ajustar seletores")
        else:
            print("  SEM ANEXO PARA TESTAR - tente com uma tarefa que tenha PDF/DOCX")
        print("=" * 60)

        print("\nFechando browser em 5 segundos...")
        await asyncio.sleep(5)

    except Exception as e:
        print(f"\nERRO: {e}")
        import traceback
        traceback.print_exc()

        await asyncio.sleep(3)
    finally:
        await browser.close()
        print("Browser fechado.")


if __name__ == "__main__":
    asyncio.run(testar_download())
