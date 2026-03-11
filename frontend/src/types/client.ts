export interface Client {
  id: number
  nome: string
  email: string
  teams_email: string
  smtp_email: string
  notification_email: string
  whatsapp: string
  status: "active" | "paused" | "expired"
  is_active: boolean
  is_expired: boolean
  expires_at: string | null
  days_remaining: number
  check_interval: number
  last_check: string | null
  tasks_completed: number
  created_at: string | null
  plan_id: number | null
  plan_name: string | null
  plan_price: number | null
  tarefas_mes: number
  limite_tarefas: number | null
  uso_percentual: number
  // Trial
  is_trial: boolean
  used_trial: boolean
  can_use_trial: boolean
  runtime_status: "idle" | "running" | "error"
  current_action: string
  // Campos extras no detalhe
  task_logs?: TaskLogEntry[]
  payments?: Payment[]
  success_rate?: number
}

export interface ClientFormData {
  nome: string
  email: string
  teams_email: string
  teams_password: string
  anthropic_key: string
  plan_id: number | null
  check_interval: number
  months: number
  smtp_email: string
  smtp_password: string
  notification_email: string
  whatsapp: string
  payment_amount: number
}

export interface Plan {
  id: number
  nome: string
  preco_mensal: number
  preco_semestral: number
  limite_tarefas: number | null
  is_trial?: boolean
  duracao_dias?: number | null
}

export interface Payment {
  id: number
  amount: number
  months: number
  created_at: string
}

export interface ClientStatus {
  id: number
  nome: string
  subscription_status: "active" | "paused" | "expired"
  days_remaining: number
  current_status: "idle" | "running" | "error"
  current_action: string | null
  last_check: string | null
  next_check: string | null
  last_task: { name: string; status: string; time: string } | null
  tasks_completed: number
  success_rate: number
  check_interval: number
  plan_name: string | null
  tarefas_mes: number
  limite_tarefas: number | null
  uso_percentual: number
  limite_atingido: boolean
}

export interface TaskLogEntry {
  id: number
  client_id?: number
  client_name?: string
  task_name: string
  discipline: string
  format: string
  status: string
  error_msg: string
  created_at: string
  // Campos de detalhe (disponiveis apenas ao buscar log individual)
  instrucoes?: string
  resposta?: string
  arquivos_enviados?: string[]
  // Debug info (apenas quando status é erro)
  debug?: {
    erro: string
    timestamp: string
    screenshot: string | null  // base64
    url: string | null
    frames: string[]
    conteudo: string | null
    turn_in_visivel: boolean | null
    turn_in_habilitado: boolean | null
    alertas_count: number | null
  } | null
}
