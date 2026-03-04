import { Page } from "@playwright/test"

/** Injeta auth no localStorage antes de navegar */
export async function injectAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("token", "fake-jwt-token")
    localStorage.setItem(
      "user",
      JSON.stringify({ username: "admin", role: "admin" })
    )
  })
}

/** Mock de todas as rotas da API para que as paginas renderizem sem backend */
export async function mockAllApiRoutes(page: Page) {
  // Dashboard stats
  await page.route("**/api/dashboard/stats", (route) =>
    route.fulfill({
      json: {
        total_clients: 5,
        active_clients: 3,
        paused_clients: 1,
        expired_clients: 1,
        tasks_today: 12,
        tasks_week: 45,
        tasks_month: 120,
        errors_24h: 2,
        success_rate: 92,
        total_tasks: 500,
        avg_per_day: 6.5,
      },
    })
  )

  // System status
  await page.route("**/api/system/status", (route) =>
    route.fulfill({
      json: {
        scheduler_running: true,
        uptime: "3d 5h",
        cpu_percent: 23,
        memory_used_gb: 1.2,
        memory_total_gb: 4.0,
        memory_percent: 30,
        scheduler_jobs: 3,
      },
    })
  )

  // Activity daily
  await page.route("**/api/activity/daily", (route) =>
    route.fulfill({
      json: [
        { weekday: "Seg", success: 8, errors: 1 },
        { weekday: "Ter", success: 10, errors: 0 },
        { weekday: "Qua", success: 6, errors: 2 },
        { weekday: "Qui", success: 9, errors: 1 },
        { weekday: "Sex", success: 12, errors: 0 },
        { weekday: "Sab", success: 0, errors: 0 },
        { weekday: "Dom", success: 0, errors: 0 },
      ],
    })
  )

  // Clients status
  await page.route("**/api/clients/status", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          nome: "Joao Silva",
          subscription_status: "active",
          plan_name: "Premium",
          success_rate: 95,
          next_check: new Date(Date.now() + 900_000).toISOString(),
          current_status: "idle",
          current_action: null,
        },
        {
          id: 2,
          nome: "Maria Souza",
          subscription_status: "active",
          plan_name: "Basico",
          success_rate: 78,
          next_check: new Date(Date.now() + 1800_000).toISOString(),
          current_status: "idle",
          current_action: null,
        },
      ],
    })
  )

  // Recent errors
  await page.route("**/api/errors/recent", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          client_name: "Maria Souza",
          task_name: "Atividade 3 - SQL",
          error_msg: "Timeout ao acessar Teams",
          created_at: new Date(Date.now() - 3600_000).toISOString(),
        },
      ],
    })
  )

  // Recent tasks (logs/recent)
  await page.route("**/api/logs/recent*", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          client_name: "Joao Silva",
          task_name: "Atividade 1 - Introducao ao Python",
          format: "py",
          status: "success",
          created_at: new Date(Date.now() - 1800_000).toISOString(),
        },
        {
          id: 2,
          client_name: "Maria Souza",
          task_name: "Atividade 2 - Banco de Dados",
          format: "sql",
          status: "error",
          created_at: new Date(Date.now() - 7200_000).toISOString(),
        },
      ],
    })
  )

  // Logs list (paginated)
  await page.route("**/api/logs?*", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: 1,
            client_name: "Joao Silva",
            task_name: "Atividade 1 - Python Basico",
            discipline: "Programacao I",
            format: "py",
            status: "success",
            error_msg: null,
            created_at: new Date(Date.now() - 1800_000).toISOString(),
          },
          {
            id: 2,
            client_name: "Maria Souza",
            task_name: "Atividade 2 - SQL Avancado",
            discipline: "Banco de Dados",
            format: "sql",
            status: "error",
            error_msg: "Timeout ao navegar",
            created_at: new Date(Date.now() - 7200_000).toISOString(),
          },
          {
            id: 3,
            client_name: "Joao Silva",
            task_name: "Atividade 3 - HTML e CSS",
            discipline: "Web I",
            format: "html",
            status: "success",
            error_msg: null,
            created_at: new Date(Date.now() - 86400_000).toISOString(),
          },
        ],
        total: 3,
        page: 1,
        pages: 1,
        per_page: 20,
      },
    })
  )

  // Logs endpoint (without query params — also match)
  await page.route("**/api/logs", (route) => {
    if (route.request().url().includes("?")) return route.fallback()
    return route.fulfill({
      json: {
        items: [],
        total: 0,
        page: 1,
        pages: 0,
        per_page: 20,
      },
    })
  })

  // Clients dropdown
  await page.route("**/api/clients?*", (route) =>
    route.fulfill({
      json: {
        items: [
          { id: 1, nome: "Joao Silva" },
          { id: 2, nome: "Maria Souza" },
        ],
        total: 2,
        page: 1,
        pages: 1,
        per_page: 200,
      },
    })
  )

  // Worker logs
  await page.route("**/api/logs/worker*", (route) =>
    route.fulfill({
      json: {
        lines: [
          "2026-03-03 10:00:00 INFO [Scheduler] Iniciando ciclo",
          "2026-03-03 10:00:05 SUCCESS [Joao Silva] Tarefa enviada",
          "2026-03-03 10:00:10 WARNING [Maria Souza] Sessao expirada",
        ],
      },
    })
  )

  // Client detail
  await page.route("**/api/clients/1*", (route) =>
    route.fulfill({
      json: {
        id: 1,
        nome: "Joao Silva",
        email: "joao@email.com",
        teams_email: "joao@teams.com",
        notification_email: "joao@notif.com",
        status: "active",
        plan_name: "Premium",
        plan_price: 49.9,
        is_trial: false,
        can_use_trial: false,
        tasks_completed: 45,
        days_remaining: 22,
        check_interval: 30,
        expires_at: new Date(Date.now() + 22 * 86400_000).toISOString(),
        created_at: new Date(Date.now() - 60 * 86400_000).toISOString(),
        last_check: new Date(Date.now() - 1800_000).toISOString(),
        uso_percentual: 45,
        tarefas_mes: 9,
        limite_tarefas: 20,
        subscription_status: "active",
        task_logs: [
          {
            id: 1,
            task_name: "Atividade 1",
            discipline: "Programacao I",
            format: "py",
            status: "success",
            created_at: new Date(Date.now() - 1800_000).toISOString(),
          },
        ],
        payments: [
          {
            id: 1,
            amount: 49.9,
            months: 1,
            created_at: new Date(Date.now() - 30 * 86400_000).toISOString(),
          },
        ],
      },
    })
  )

  // Processadas
  await page.route("**/api/clients/1/processadas", (route) =>
    route.fulfill({
      json: { items: [], total: 0 },
    })
  )

  // Financeiro resumo
  await page.route("**/api/financeiro/resumo", (route) =>
    route.fulfill({
      json: {
        receita: { mes: 149.7, total: 898.2 },
        custos: { mes: 12.5, total: 75.0 },
        lucro: { mes: 137.2, total: 823.2 },
        clientes: { total: 5, ativos: 3, expirados: 1, pausados: 1 },
        clientes_por_plano: [
          { plano: "Premium", preco: 49.9, quantidade: 2, receita_potencial: 99.8 },
          { plano: "Basico", preco: 29.9, quantidade: 1, receita_potencial: 29.9 },
        ],
        tarefas: { mes: 45, sucesso: 42 },
        margem_lucro: 91.6,
      },
    })
  )

  // Financeiro clientes
  await page.route("**/api/financeiro/clientes", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          nome: "Joao Silva",
          email: "joao@email.com",
          plano: "Premium",
          preco_plano: 49.9,
          status: "ativo",
          dias_restantes: 22,
          expires_at: new Date(Date.now() + 22 * 86400_000).toISOString(),
          pagamentos_total: 149.7,
          ultimo_pagamento: new Date(Date.now() - 30 * 86400_000).toISOString(),
          ultimo_valor: 49.9,
          custos_mes: 5.2,
          custos_total: 31.2,
          lucro_estimado: 44.7,
          tarefas_mes: 9,
          limite_tarefas: 20,
          uso_percentual: 45,
          tarefas_total: 45,
          tarefas_sucesso: 43,
          taxa_sucesso: 95,
          created_at: new Date(Date.now() - 60 * 86400_000).toISOString(),
        },
      ],
    })
  )

  // Financeiro receita mensal
  await page.route("**/api/financeiro/receita-mensal", (route) =>
    route.fulfill({
      json: [
        { mes: "Out", receita: 99.8, custos: 8.5, lucro: 91.3 },
        { mes: "Nov", receita: 129.7, custos: 10.2, lucro: 119.5 },
        { mes: "Dez", receita: 149.7, custos: 12.5, lucro: 137.2 },
      ],
    })
  )
}
