export interface DashboardStats {
  total_clients: number
  active_clients: number
  expired_clients: number
  paused_clients: number
  tasks_today: number
  tasks_week: number
  tasks_month: number
  total_tasks: number
  success_rate: number
  errors_24h: number
  avg_per_day: number
}

export interface SystemStatus {
  uptime: string
  memory_used_gb: number
  memory_total_gb: number
  memory_percent: number
  cpu_percent: number
  scheduler_running: boolean
  scheduler_jobs: number
}

export interface ActivityDay {
  date: string
  weekday: string
  success: number
  errors: number
  other: number
  total: number
}

export interface SchedulerJob {
  id: string
  name: string
  next_run: string | null
  next_run_formatted: string
}

export interface SchedulerStatus {
  running: boolean
  jobs: SchedulerJob[]
  queue: Record<string, unknown>
}

export interface RecentError {
  id: number
  client_name: string
  task_name: string
  error_msg: string
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}
