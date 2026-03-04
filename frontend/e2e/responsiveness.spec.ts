import { test, expect } from "@playwright/test"
import { injectAuth, mockAllApiRoutes } from "./helpers"

// ─────────────────────────────────────────────────────────────
// Setup: auth + mocks antes de cada teste
// ─────────────────────────────────────────────────────────────

test.beforeEach(async ({ page }) => {
  await injectAuth(page)
  await mockAllApiRoutes(page)
})

// ─────────────────────────────────────────────────────────────
// FASE 1 — Sidebar e layout
// ─────────────────────────────────────────────────────────────

test.describe("Sidebar e layout responsivo", () => {
  test("desktop: sidebar fixa visivel, sem hamburger", async ({ page, browserName }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/")
    await expect(page.locator("aside")).toBeVisible()
    // Hamburger nao deve estar visivel no desktop
    await expect(page.locator('button:has(svg.lucide-menu)')).toBeHidden()
  })

  test("mobile: sidebar escondida, hamburger visivel", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")
    // Sidebar fixa deve estar escondida
    await expect(page.locator("aside")).toBeHidden()
    // Hamburger deve estar visivel
    await expect(page.locator('button:has(svg.lucide-menu)')).toBeVisible()
  })

  test("mobile: hamburger abre e fecha sidebar como drawer", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")

    // Clicar no hamburger
    await page.locator('button:has(svg.lucide-menu)').click()

    // Sheet (drawer) deve aparecer com conteudo da sidebar
    const sheet = page.locator('[data-slot="sheet-content"]')
    await expect(sheet).toBeVisible()
    await expect(sheet.locator("text=Teams Solver")).toBeVisible()
    await expect(sheet.locator("text=Dashboard")).toBeVisible()
    await expect(sheet.locator("text=Clientes")).toBeVisible()
    await expect(sheet.locator("text=Logs")).toBeVisible()
  })

  test("mobile: clicar em nav link fecha o drawer", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")

    // Abrir sidebar
    await page.locator('button:has(svg.lucide-menu)').click()
    const sheet = page.locator('[data-slot="sheet-content"]')
    await expect(sheet).toBeVisible()

    // Clicar em "Logs"
    await sheet.locator('a:has-text("Logs")').click()

    // Sheet deve fechar
    await expect(sheet).toBeHidden()

    // Deve ter navegado para /app/logs
    await expect(page).toHaveURL(/\/app\/logs/)
  })

  test("mobile: main nao tem margin-left de 220px", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")
    const mainWrapper = page.locator("aside + div")
    const marginLeft = await mainWrapper.evaluate((el) =>
      window.getComputedStyle(el).marginLeft
    )
    expect(marginLeft).toBe("0px")
  })

  test("desktop: main tem margin-left de 220px", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/")
    const mainWrapper = page.locator("aside + div")
    const marginLeft = await mainWrapper.evaluate((el) =>
      window.getComputedStyle(el).marginLeft
    )
    expect(marginLeft).toBe("220px")
  })
})

// ─────────────────────────────────────────────────────────────
// FASE 2 — Filtros responsivos (logs)
// ─────────────────────────────────────────────────────────────

test.describe("Filtros responsivos (logs)", () => {
  test("mobile: filtros nao estourem o viewport", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/logs")
    await page.waitForSelector("text=Buscar")

    const viewport = page.viewportSize()!
    // Selecionar o grid de filtros pelo data-slot do CardContent
    const filterGrid = page.locator('[data-slot="card-content"]').first()
    const box = await filterGrid.boundingBox()

    // Container de filtros nao deve ultrapassar o viewport
    expect(box).toBeTruthy()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 2) // 2px tolerance
  })

  test("desktop: filtros em 5 colunas (single row)", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/logs")
    await page.waitForSelector("text=Buscar")

    // Busca e Cliente devem estar na mesma linha (Y similar)
    const clienteLabel = page.locator("label", { hasText: "Cliente" })
    const buscarLabel = page.locator("label", { hasText: "Buscar" })

    const clienteBox = await clienteLabel.boundingBox()
    const buscarBox = await buscarLabel.boundingBox()

    expect(clienteBox).toBeTruthy()
    expect(buscarBox).toBeTruthy()
    // Mesmo Y (mesma linha, tolerancia de 5px)
    expect(Math.abs(clienteBox!.y - buscarBox!.y)).toBeLessThan(5)
  })
})

// ─────────────────────────────────────────────────────────────
// FASE 3 — Tabelas: colunas ocultas no mobile
// ─────────────────────────────────────────────────────────────

test.describe("Tabelas com colunas responsivas", () => {
  test("logs mobile: Disciplina e Erro ocultos", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/logs")
    await page.waitForSelector("text=Joao Silva")

    // Headers Disciplina e Erro devem estar ocultos
    const disciplinaHead = page.locator("th", { hasText: "Disciplina" })
    const erroHead = page.locator("th", { hasText: "Erro" })

    await expect(disciplinaHead).toBeHidden()
    await expect(erroHead).toBeHidden()

    // Data e Cliente devem estar visiveis
    await expect(page.locator("th", { hasText: "Data" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Cliente" })).toBeVisible()
  })

  test("logs desktop: todas as colunas visiveis", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/logs")
    await page.waitForSelector("text=Joao Silva")

    await expect(page.locator("th", { hasText: "Disciplina" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Erro" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Status" })).toBeVisible()
  })

  test("dashboard mobile: Plano e Sucesso% ocultos nos clientes", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")
    await page.waitForSelector("text=Joao Silva")

    // Na tabela Status dos Clientes
    const clientesSection = page.locator("text=Status dos Clientes").locator("..").locator("..")
    await expect(clientesSection.locator("th", { hasText: "Plano" })).toBeHidden()
    await expect(clientesSection.locator("th", { hasText: "Sucesso%" })).toBeHidden()
  })

  test("dashboard mobile: Formato oculto nas tarefas recentes", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")
    await page.waitForSelector("text=Tarefas Recentes")

    const tarefasSection = page.locator("text=Tarefas Recentes").locator("..").locator("..")
    await expect(tarefasSection.locator("th", { hasText: "Formato" })).toBeHidden()
  })

  test("financeiro mobile: Custos/Mes e Lucro ocultos", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/financeiro")
    await page.waitForSelector("text=Joao Silva")

    await expect(page.locator("th", { hasText: "Custos/Mes" })).toBeHidden()
    await expect(page.locator("th", { hasText: "Lucro Est." })).toBeHidden()
  })

  test("client-detail mobile: Disciplina e Formato ocultos no historico", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/clients/1")
    await page.waitForSelector("text=Historico de Tarefas")

    const historicoSection = page.locator("text=Historico de Tarefas").locator("..").locator("..")
    await expect(historicoSection.locator("th", { hasText: "Disciplina" })).toBeHidden()
    await expect(historicoSection.locator("th", { hasText: "Formato" })).toBeHidden()
  })
})

// ─────────────────────────────────────────────────────────────
// FASE 4 — Cards responsivos
// ─────────────────────────────────────────────────────────────

test.describe("Cards responsivos", () => {
  test("client-detail: plan usage bar nao causa overflow no mobile", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/clients/1")
    await page.waitForSelector("text=Premium")

    const viewport = page.viewportSize()!

    // Verificar que nao ha overflow horizontal no body
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth)
    expect(bodyWidth).toBeLessThanOrEqual(viewport.width + 2)
  })
})

// ─────────────────────────────────────────────────────────────
// FASE 5 — Alturas fixas responsivas
// ─────────────────────────────────────────────────────────────

test.describe("Alturas fixas responsivas", () => {
  test("terminal mobile: max-height menor que desktop", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/logs")
    // Esperar o terminal renderizar (usa o locator da classe bg do terminal body)
    await page.locator(".bg-\\[\\#0a0a0c\\]").waitFor({ state: "visible" })

    const terminal = page.locator(".font-mono.overflow-y-auto")
    const maxHeight = await terminal.evaluate((el) =>
      window.getComputedStyle(el).maxHeight
    )
    expect(maxHeight).toBe("200px")
  })

  test("terminal desktop: max-height 350px", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/logs")
    await page.waitForSelector("text=Logs do Worker")

    const terminal = page.locator(".font-mono.overflow-y-auto")
    const maxHeight = await terminal.evaluate((el) =>
      window.getComputedStyle(el).maxHeight
    )
    expect(maxHeight).toBe("350px")
  })
})

// ─────────────────────────────────────────────────────────────
// FASE 6 — Espacamento e tipografia
// ─────────────────────────────────────────────────────────────

test.describe("Espacamento e tipografia", () => {
  test("page header: font-size menor no mobile", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Somente mobile")
    await page.goto("/app/")
    const h1 = page.locator("h1", { hasText: "Dashboard" })
    const fontSize = await h1.evaluate((el) =>
      window.getComputedStyle(el).fontSize
    )
    // text-lg = 18px (1.125rem)
    expect(parseFloat(fontSize)).toBeLessThanOrEqual(18)
  })

  test("page header: font-size maior no desktop", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/")
    const h1 = page.locator("h1", { hasText: "Dashboard" })
    const fontSize = await h1.evaluate((el) =>
      window.getComputedStyle(el).fontSize
    )
    // text-xl = 20px (1.25rem)
    expect(parseFloat(fontSize)).toBeGreaterThanOrEqual(20)
  })
})

// ─────────────────────────────────────────────────────────────
// GLOBAL — Sem overflow horizontal em nenhuma pagina
// ─────────────────────────────────────────────────────────────

test.describe("Sem overflow horizontal", () => {
  const pages = [
    { name: "Dashboard", url: "/app/" },
    { name: "Logs", url: "/app/logs" },
    { name: "Financeiro", url: "/app/financeiro" },
    { name: "Client Detail", url: "/app/clients/1" },
  ]

  for (const pg of pages) {
    test(`mobile: ${pg.name} sem overflow horizontal`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name !== "mobile", "Somente mobile")
      await page.goto(pg.url)
      // Esperar conteudo carregar
      await page.waitForTimeout(1000)

      const viewport = page.viewportSize()!
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
      expect(scrollWidth).toBeLessThanOrEqual(viewport.width + 2)
    })
  }
})

// ─────────────────────────────────────────────────────────────
// REGRESSAO — Desktop deve manter comportamento anterior
// ─────────────────────────────────────────────────────────────

test.describe("Regressao desktop", () => {
  test("dashboard: todas as secoes renderizam", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/")

    await expect(page.locator("h1", { hasText: "Dashboard" })).toBeVisible()
    await expect(page.locator("text=Total Clientes")).toBeVisible()
    await expect(page.locator("text=Atividade (7 dias)")).toBeVisible()
    await expect(page.locator("text=Status dos Clientes")).toBeVisible()
    await expect(page.locator("text=Tarefas Recentes")).toBeVisible()
    await expect(page.locator("text=Erros Recentes")).toBeVisible()
  })

  test("logs: tabela completa com todos os filtros", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/logs")

    await expect(page.locator("text=Logs de Execucao")).toBeVisible()
    await expect(page.locator("label", { hasText: "Cliente" })).toBeVisible()
    await expect(page.locator("label", { hasText: "Status" })).toBeVisible()
    await expect(page.locator("label", { hasText: "De" })).toBeVisible()
    await expect(page.locator("label", { hasText: "Ate" })).toBeVisible()
    await expect(page.locator("label", { hasText: "Buscar" })).toBeVisible()

    // Todas as colunas da tabela
    await expect(page.locator("th", { hasText: "Data" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Cliente" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Tarefa" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Disciplina" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Formato" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Status" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Erro" })).toBeVisible()
  })

  test("financeiro: tabela com todas as colunas", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "Somente desktop")
    await page.goto("/app/financeiro")
    await page.waitForSelector("text=Joao Silva")

    await expect(page.locator("th", { hasText: "Custos/Mes" })).toBeVisible()
    await expect(page.locator("th", { hasText: "Lucro Est." })).toBeVisible()
  })
})
