/** Intervalos de refresh para TanStack Query (em ms). */
export const REFRESH_INTERVALS = {
  DASHBOARD_STATS: 10_000,
  SYSTEM_STATUS: 15_000,
  CLIENTS_STATUS: 10_000,
  ACTIVITY_CHART: 30_000,
  RECENT_TASKS: 10_000,
  RECENT_ERRORS: 15_000,
  LOGS: 10_000,
  SERVER_LOGS: 2_000,
} as const

export const PAGE_SIZE = 20
