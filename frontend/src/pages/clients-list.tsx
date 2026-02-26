import { useState, useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { motion } from "framer-motion"
import {
  Users,
  UserCheck,
  UserX,
  UserMinus,
  Plus,
  Play,
  Pause,
  Search,
  Loader2,
} from "lucide-react"
import { toast } from "sonner"

import api from "@/lib/api"
import { cn, timeAgo } from "@/lib/utils"
import { REFRESH_INTERVALS } from "@/lib/constants"
import { useDebounce } from "@/hooks/use-debounce"
import type { Client } from "@/types/client"
import type { PaginatedResponse } from "@/types/api"

import { PageHeader } from "@/components/shared/page-header"
import { StatusBadge } from "@/components/shared/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

type StatusFilter = "all" | "active" | "expired" | "paused"

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04 },
  },
}

const item = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0 },
}

export function ClientsListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [searchInput, setSearchInput] = useState("")
  const debouncedSearch = useDebounce(searchInput, 300)

  // ── Query: fetch clients ──
  const { data, isLoading, isError } = useQuery({
    queryKey: ["clients", statusFilter, debouncedSearch],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (statusFilter !== "all") params.set("status", statusFilter)
      if (debouncedSearch) params.set("search", debouncedSearch)
      const res = await api.get<PaginatedResponse<Client>>(
        `/clients?${params.toString()}`
      )
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.CLIENTS_STATUS,
  })

  const clients = data?.items ?? []

  // ── Stats computed from full list ──
  const stats = useMemo(() => {
    const all = clients
    return {
      total: all.length,
      active: all.filter((c) => c.status === "active").length,
      expired: all.filter((c) => c.status === "expired").length,
      paused: all.filter((c) => c.status === "paused").length,
    }
  }, [clients])

  // ── Mutation: run all clients ──
  const runAll = useMutation({
    mutationFn: () => api.post("/clients/run-all"),
    onSuccess: () => {
      toast.success("Execucao iniciada para todos os clientes ativos")
      queryClient.invalidateQueries({ queryKey: ["clients"] })
    },
    onError: () => {
      toast.error("Erro ao iniciar execucao em lote")
    },
  })

  // ── Mutation: toggle client active/paused ──
  const toggle = useMutation({
    mutationFn: (id: number) => api.post(`/clients/${id}/toggle`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] })
      toast.success("Status do cliente atualizado")
    },
    onError: () => {
      toast.error("Erro ao alterar status do cliente")
    },
  })

  // ── Stat card config ──
  const statCards = [
    {
      label: "Total",
      value: stats.total,
      icon: Users,
      color: "text-zinc-400",
      bg: "bg-zinc-500/10",
    },
    {
      label: "Ativos",
      value: stats.active,
      icon: UserCheck,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
    },
    {
      label: "Expirados",
      value: stats.expired,
      icon: UserX,
      color: "text-red-500",
      bg: "bg-red-500/10",
    },
    {
      label: "Pausados",
      value: stats.paused,
      icon: UserMinus,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
    },
  ]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* ── Header ── */}
      <PageHeader
        title="Clientes"
        description="Gerenciamento de clientes cadastrados"
      >
        <Button
          variant="outline"
          size="sm"
          disabled={runAll.isPending || stats.active === 0}
          onClick={() => runAll.mutate()}
        >
          {runAll.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Rodar Todos ({stats.active})
        </Button>
        <Button size="sm" asChild>
          <Link to="/clients/new">
            <Plus className="h-4 w-4" />
            Novo Cliente
          </Link>
        </Button>
      </PageHeader>

      {/* ── Stat Cards ── */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 gap-3 lg:grid-cols-4"
      >
        {statCards.map((s) => (
          <motion.div key={s.label} variants={item}>
            <Card className="py-4">
              <CardContent className="flex items-center gap-3">
                <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg", s.bg)}>
                  <s.icon className={cn("h-4 w-4", s.color)} />
                </div>
                <div>
                  <p className="text-2xl font-semibold tracking-tight">
                    {isLoading ? <Skeleton className="h-7 w-10" /> : s.value}
                  </p>
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* ── Filter Bar ── */}
      <Card className="py-4">
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Tabs
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as StatusFilter)}
          >
            <TabsList>
              <TabsTrigger value="all">Todos</TabsTrigger>
              <TabsTrigger value="active">Ativos</TabsTrigger>
              <TabsTrigger value="expired">Expirados</TabsTrigger>
              <TabsTrigger value="paused">Pausados</TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="relative w-full sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Buscar cliente..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-9"
            />
          </div>
        </CardContent>
      </Card>

      {/* ── Table ── */}
      <Card className="py-0 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Cliente</TableHead>
              <TableHead>Email Teams</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Plano</TableHead>
              <TableHead>Uso</TableHead>
              <TableHead>Assinatura</TableHead>
              <TableHead>Ultimo Check</TableHead>
              <TableHead className="pr-4 text-right">Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 8 }).map((_, j) => (
                    <TableCell key={j} className={j === 0 ? "pl-4" : ""}>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : isError ? (
              <TableRow>
                <TableCell colSpan={8} className="h-32 text-center text-muted-foreground">
                  Erro ao carregar clientes
                </TableCell>
              </TableRow>
            ) : clients.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-32 text-center text-muted-foreground">
                  Nenhum cliente encontrado
                </TableCell>
              </TableRow>
            ) : (
              clients.map((client) => {
                const usagePercent = client.uso_percentual
                const daysRemaining = client.days_remaining
                const totalDays = client.expires_at
                  ? Math.max(
                      1,
                      Math.ceil(
                        (new Date(client.expires_at).getTime() -
                          (client.created_at
                            ? new Date(client.created_at).getTime()
                            : Date.now())) /
                          86400000
                      )
                    )
                  : 30
                const subscriptionPercent = Math.min(
                  100,
                  Math.max(0, ((totalDays - daysRemaining) / totalDays) * 100)
                )

                return (
                  <TableRow
                    key={client.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/clients/${client.id}`)}
                  >
                    {/* Cliente */}
                    <TableCell className="pl-4">
                      <div>
                        <p className="font-medium">{client.nome}</p>
                        <p className="text-xs text-muted-foreground">
                          {client.email}
                        </p>
                      </div>
                    </TableCell>

                    {/* Email Teams */}
                    <TableCell>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                        {client.teams_email}
                      </code>
                    </TableCell>

                    {/* Status */}
                    <TableCell>
                      <StatusBadge status={client.status} />
                    </TableCell>

                    {/* Plano */}
                    <TableCell>
                      <span className="text-sm">
                        {client.plan_name ?? "Sem plano"}
                      </span>
                    </TableCell>

                    {/* Uso */}
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress
                          value={usagePercent}
                          className={cn(
                            "h-1.5 w-16",
                            usagePercent >= 90
                              ? "[&>[data-slot=progress-indicator]]:bg-red-500"
                              : usagePercent >= 70
                              ? "[&>[data-slot=progress-indicator]]:bg-amber-500"
                              : "[&>[data-slot=progress-indicator]]:bg-emerald-500"
                          )}
                        />
                        <span className="text-xs text-muted-foreground">
                          {client.tarefas_mes}/
                          {client.limite_tarefas ?? "Ilim."}
                        </span>
                      </div>
                    </TableCell>

                    {/* Assinatura */}
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress
                          value={subscriptionPercent}
                          className={cn(
                            "h-1.5 w-14",
                            daysRemaining <= 3
                              ? "[&>[data-slot=progress-indicator]]:bg-red-500"
                              : daysRemaining <= 7
                              ? "[&>[data-slot=progress-indicator]]:bg-amber-500"
                              : "[&>[data-slot=progress-indicator]]:bg-emerald-500"
                          )}
                        />
                        <span className="text-xs text-muted-foreground">
                          {daysRemaining}d
                        </span>
                      </div>
                    </TableCell>

                    {/* Ultimo Check */}
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {client.last_check
                          ? timeAgo(client.last_check)
                          : "Nunca"}
                      </span>
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="pr-4 text-right">
                      <div
                        className="flex items-center justify-end gap-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <TooltipProvider>
                          {client.status === "active" ? (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon-xs"
                                  onClick={() => toggle.mutate(client.id)}
                                  disabled={toggle.isPending}
                                >
                                  <Pause className="h-3.5 w-3.5 text-amber-500" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Pausar</TooltipContent>
                            </Tooltip>
                          ) : (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon-xs"
                                  onClick={() => toggle.mutate(client.id)}
                                  disabled={toggle.isPending}
                                >
                                  <Play className="h-3.5 w-3.5 text-emerald-500" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Ativar</TooltipContent>
                            </Tooltip>
                          )}
                        </TooltipProvider>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </Card>
    </motion.div>
  )
}
