import { useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import {
  Users,
  UserCheck,
  CalendarDays,
  CalendarRange,
  TrendingUp,
  BarChart3,
  Cpu,
  HardDrive,
  Clock,
  Layers,
  Activity,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
} from "lucide-react"

import { PageHeader } from "@/components/shared/page-header"
import { StatusBadge } from "@/components/shared/status-badge"
import { FormatBadge } from "@/components/shared/format-badge"
import { ActivityDetailDialog } from "@/components/shared/activity-detail-dialog"
import api from "@/lib/api"
import { timeAgo, timeUntil, cn } from "@/lib/utils"
import { REFRESH_INTERVALS } from "@/lib/constants"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Progress } from "@/components/ui/progress"

import type {
  DashboardStats,
  SystemStatus,
  ActivityDay,
  RecentError,
} from "@/types/api"
import type { ClientStatus, TaskLogEntry } from "@/types/client"

// ─── Live indicator with pulse ────────────────────────────────────────────────

function LiveIndicator() {
  return (
    <span className="relative flex h-2.5 w-2.5">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
      <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
    </span>
  )
}

// ─── Stats card ───────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: string | number
  icon: React.ReactNode
  description?: string
  iconClassName?: string
}

function StatCard({ label, value, icon, description, iconClassName }: StatCardProps) {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-lg",
              iconClassName || "bg-zinc-500/10 text-zinc-400"
            )}
          >
            {icon}
          </div>
        </div>
        <p className="mt-2 text-xl font-bold tracking-tight sm:text-2xl">{value}</p>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  )
}

function StatCardSkeleton() {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-5">
        <div className="flex items-center justify-between">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-8 w-8 rounded-lg" />
        </div>
        <Skeleton className="mt-3 h-7 w-16" />
        <Skeleton className="mt-2 h-3 w-28" />
      </CardContent>
    </Card>
  )
}

// ─── System status dot ────────────────────────────────────────────────────────

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        ok ? "bg-emerald-500" : "bg-red-500"
      )}
    />
  )
}

// ─── Custom tooltip for chart ─────────────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ value: number; name: string; color: string }>
  label?: string
}) {
  if (!active || !payload) return null
  return (
    <div className="rounded-lg border border-white/[0.08] bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur-sm">
      <p className="mb-1 text-xs font-medium text-zinc-400">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 text-xs">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-zinc-300">
            {entry.name === "success" ? "Sucesso" : "Erros"}: {entry.value}
          </span>
        </div>
      ))}
    </div>
  )
}

// ─── Dashboard page ───────────────────────────────────────────────────────────

export function DashboardPage() {
  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [secondsAgo, setSecondsAgo] = useState(0)
  const [selectedLogId, setSelectedLogId] = useState<number | null>(null)
  const [logDialogOpen, setLogDialogOpen] = useState(false)
  const queryClient = useQueryClient()

  // Tick every second for the "updated X seconds ago" display
  useEffect(() => {
    const interval = setInterval(() => {
      setSecondsAgo(Math.floor((Date.now() - lastRefresh.getTime()) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [lastRefresh])

  // ── Queries ───────────────────────────────────────────────────────────

  const statsQuery = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: async () => {
      const res = await api.get<DashboardStats>("/dashboard/stats")
      setLastRefresh(new Date())
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.DASHBOARD_STATS,
  })

  const systemQuery = useQuery({
    queryKey: ["system-status"],
    queryFn: async () => {
      const res = await api.get<SystemStatus>("/system/status")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.SYSTEM_STATUS,
  })

  const activityQuery = useQuery({
    queryKey: ["activity-daily"],
    queryFn: async () => {
      const res = await api.get<ActivityDay[]>("/activity/daily")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.ACTIVITY_CHART,
  })

  const clientsQuery = useQuery({
    queryKey: ["clients-status"],
    queryFn: async () => {
      const res = await api.get<ClientStatus[]>("/clients/status")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.CLIENTS_STATUS,
  })

  const errorsQuery = useQuery({
    queryKey: ["recent-errors"],
    queryFn: async () => {
      const res = await api.get<RecentError[]>("/errors/recent")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.RECENT_ERRORS,
  })

  const logsQuery = useQuery({
    queryKey: ["recent-tasks"],
    queryFn: async () => {
      const res = await api.get<TaskLogEntry[]>("/logs/recent", {
        params: { limit: 10 },
      })
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.RECENT_TASKS,
  })

  const stats = statsQuery.data
  const system = systemQuery.data
  const activity = activityQuery.data
  const clients = clientsQuery.data
  const errors = errorsQuery.data
  const recentTasks = logsQuery.data

  // Find currently running client
  const runningClient = clients?.find((c) => c.current_status === "running")

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <PageHeader title="Dashboard" description="Visao geral do sistema">
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 pr-2.5 text-emerald-400"
          >
            <LiveIndicator />
            Live
          </Badge>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <RefreshCw className="h-3 w-3" />
            Atualizado ha {secondsAgo}s
          </span>
        </div>
      </PageHeader>

      {/* ── Stats cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        {statsQuery.isLoading ? (
          Array.from({ length: 6 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard
              label="Total Clientes"
              value={stats?.total_clients ?? 0}
              icon={<Users className="h-4 w-4" />}
              iconClassName="bg-zinc-500/10 text-zinc-400"
              description={`${stats?.paused_clients ?? 0} pausados, ${stats?.expired_clients ?? 0} expirados`}
            />
            <StatCard
              label="Ativos"
              value={stats?.active_clients ?? 0}
              icon={<UserCheck className="h-4 w-4" />}
              iconClassName="bg-emerald-500/10 text-emerald-400"
              description="Assinatura vigente"
            />
            <StatCard
              label="Hoje"
              value={stats?.tasks_today ?? 0}
              icon={<CalendarDays className="h-4 w-4" />}
              iconClassName="bg-blue-500/10 text-blue-400"
              description={`${stats?.errors_24h ?? 0} erros nas ultimas 24h`}
            />
            <StatCard
              label="Semana"
              value={stats?.tasks_week ?? 0}
              icon={<CalendarRange className="h-4 w-4" />}
              iconClassName="bg-violet-500/10 text-violet-400"
              description={`${stats?.tasks_month ?? 0} no mes`}
            />
            <StatCard
              label="Taxa Sucesso"
              value={`${stats?.success_rate ?? 0}%`}
              icon={<TrendingUp className="h-4 w-4" />}
              iconClassName="bg-amber-500/10 text-amber-400"
              description={`${stats?.total_tasks ?? 0} tarefas total`}
            />
            <StatCard
              label="Media/Dia"
              value={stats?.avg_per_day?.toFixed(1) ?? "0"}
              icon={<BarChart3 className="h-4 w-4" />}
              iconClassName="bg-cyan-500/10 text-cyan-400"
              description="Tarefas por dia"
            />
          </>
        )}
      </div>

      {/* ── System status bar ───────────────────────────────────────────── */}
      <Card className="gap-0 py-3">
        <CardContent className="px-5">
          {systemQuery.isLoading ? (
            <div className="flex items-center gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-4 w-24" />
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              {/* Scheduler */}
              <div className="flex items-center gap-2 text-xs">
                <StatusDot ok={system?.scheduler_running ?? false} />
                <span className="text-muted-foreground">Scheduler</span>
                <span className="font-medium">
                  {system?.scheduler_running ? "OK" : "Parado"}
                </span>
              </div>

              {/* Uptime */}
              <div className="flex items-center gap-2 text-xs">
                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Uptime</span>
                <span className="font-medium">{system?.uptime ?? "—"}</span>
              </div>

              {/* CPU */}
              <div className="flex items-center gap-2 text-xs">
                <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">CPU</span>
                <span className="font-medium">{system?.cpu_percent ?? 0}%</span>
              </div>

              {/* RAM */}
              <div className="flex items-center gap-2 text-xs">
                <HardDrive className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">RAM</span>
                <span className="font-medium">
                  {system?.memory_used_gb?.toFixed(1) ?? 0}/
                  {system?.memory_total_gb?.toFixed(1) ?? 0} GB
                </span>
                <Progress
                  value={system?.memory_percent ?? 0}
                  className="h-1.5 w-16"
                />
              </div>

              {/* Jobs */}
              <div className="flex items-center gap-2 text-xs">
                <Layers className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Jobs</span>
                <span className="font-medium">{system?.scheduler_jobs ?? 0}</span>
              </div>

              {/* Separator + Running client */}
              {runningClient && (
                <>
                  <div className="h-4 w-px bg-border" />
                  <Badge
                    variant="outline"
                    className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                  >
                    <Activity className="h-3 w-3 animate-pulse" />
                    {runningClient.nome}
                    {runningClient.current_action
                      ? ` — ${runningClient.current_action}`
                      : ""}
                  </Badge>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Activity chart + Clients table ──────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Activity chart (5 columns) */}
        <Card className="lg:col-span-5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Atividade (7 dias)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {activityQuery.isLoading ? (
              <Skeleton className="h-[180px] sm:h-[220px] w-full rounded-lg" />
            ) : (
              <div className="h-[180px] sm:h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={activity ?? []}
                  margin={{ top: 4, right: 4, bottom: 0, left: -20 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(255,255,255,0.04)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="weekday"
                    tick={{ fontSize: 11, fill: "#71717a" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#71717a" }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    content={<ChartTooltip />}
                    cursor={{ fill: "rgba(255,255,255,0.03)" }}
                  />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }}
                    formatter={(value: string) =>
                      value === "success" ? "Sucesso" : "Erros"
                    }
                  />
                  <Bar
                    dataKey="success"
                    stackId="a"
                    fill="#10b981"
                    radius={[0, 0, 0, 0]}
                    maxBarSize={28}
                  />
                  <Bar
                    dataKey="errors"
                    stackId="a"
                    fill="#ef4444"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={28}
                  />
                </BarChart>
              </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Clients status table (7 columns) */}
        <Card className="lg:col-span-7">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Status dos Clientes
            </CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            {clientsQuery.isLoading ? (
              <div className="space-y-3 px-6">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-6">Cliente</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="hidden sm:table-cell">Plano</TableHead>
                    <TableHead className="hidden sm:table-cell text-right">Sucesso%</TableHead>
                    <TableHead className="pr-6 text-right">
                      Proximo check
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {clients && clients.length > 0 ? (
                    clients.slice(0, 8).map((client) => (
                      <TableRow key={client.id}>
                        <TableCell className="pl-6 font-medium">
                          {client.nome}
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={client.subscription_status} />
                        </TableCell>
                        <TableCell className="hidden sm:table-cell text-muted-foreground">
                          {client.plan_name ?? "—"}
                        </TableCell>
                        <TableCell className="hidden sm:table-cell text-right">
                          <span
                            className={cn(
                              "font-mono text-sm",
                              client.success_rate >= 80
                                ? "text-emerald-400"
                                : client.success_rate >= 50
                                  ? "text-amber-400"
                                  : "text-red-400"
                            )}
                          >
                            {client.success_rate}%
                          </span>
                        </TableCell>
                        <TableCell className="pr-6 text-right text-xs text-muted-foreground">
                          {client.next_check ? timeUntil(client.next_check) : "—"}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell
                        colSpan={5}
                        className="py-8 text-center text-muted-foreground"
                      >
                        Nenhum cliente cadastrado
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Recent tasks + Recent errors ────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Recent tasks table (8 columns) */}
        <Card className="lg:col-span-8">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Tarefas Recentes
            </CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            {logsQuery.isLoading ? (
              <div className="space-y-3 px-6">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-6">Cliente</TableHead>
                    <TableHead>Tarefa</TableHead>
                    <TableHead className="hidden sm:table-cell">Formato</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="pr-6 text-right">Quando</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentTasks && recentTasks.length > 0 ? (
                    recentTasks.map((task) => (
                      <TableRow
                        key={task.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => {
                          setSelectedLogId(task.id)
                          setLogDialogOpen(true)
                        }}
                      >
                        <TableCell className="pl-6 font-medium">
                          {task.client_name ?? "—"}
                        </TableCell>
                        <TableCell
                          className="max-w-[120px] sm:max-w-[200px] truncate text-muted-foreground"
                          title={task.task_name}
                        >
                          {task.task_name}
                        </TableCell>
                        <TableCell className="hidden sm:table-cell">
                          {task.format ? (
                            <FormatBadge format={task.format} />
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={task.status} />
                        </TableCell>
                        <TableCell className="pr-6 text-right text-xs text-muted-foreground">
                          {timeAgo(task.created_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell
                        colSpan={5}
                        className="py-8 text-center text-muted-foreground"
                      >
                        Nenhuma tarefa recente
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Recent errors (4 columns) */}
        <Card className="lg:col-span-4">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              Erros Recentes
            </CardTitle>
          </CardHeader>
          <CardContent>
            {errorsQuery.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            ) : errors && errors.length > 0 ? (
              <div className="space-y-2.5">
                {errors.slice(0, 6).map((error) => (
                  <div
                    key={error.id}
                    className={cn(
                      "rounded-lg border border-white/[0.04] bg-white/[0.02] p-3",
                      "border-l-2 border-l-red-500/60"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-zinc-300">
                        {error.client_name}
                      </span>
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        {timeAgo(error.created_at)}
                      </span>
                    </div>
                    {error.task_name && (
                      <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                        {error.task_name}
                      </p>
                    )}
                    <p
                      className="mt-1 line-clamp-2 text-xs text-red-400/80"
                      title={error.error_msg}
                    >
                      {error.error_msg}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <CheckCircle2 className="mb-2 h-8 w-8 text-emerald-500/50" />
                <p className="text-xs text-muted-foreground">
                  Nenhum erro recente
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Task Detail Dialog */}
      <ActivityDetailDialog
        logId={selectedLogId}
        open={logDialogOpen}
        onOpenChange={setLogDialogOpen}
        onUndoSuccess={() => queryClient.invalidateQueries({ queryKey: ["recent-tasks"] })}
      />
    </div>
  )
}
