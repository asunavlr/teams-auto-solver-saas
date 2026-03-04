import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Search, Terminal, Pause, Play, Trash2, ArrowDown, Eye } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { PageHeader } from "@/components/shared/page-header"
import { StatusBadge } from "@/components/shared/status-badge"
import { FormatBadge } from "@/components/shared/format-badge"
import { EmptyState } from "@/components/shared/empty-state"
import { ActivityDetailDialog } from "@/components/shared/activity-detail-dialog"
import { useDebounce } from "@/hooks/use-debounce"
import api from "@/lib/api"
import { cn, formatDateTime } from "@/lib/utils"
import { REFRESH_INTERVALS } from "@/lib/constants"
import type { PaginatedResponse } from "@/types/api"
import type { TaskLogEntry, Client } from "@/types/client"

// ============================================
// LOGS TABLE SECTION
// ============================================

export function LogsPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [clientFilter, setClientFilter] = useState<string>("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [searchInput, setSearchInput] = useState("")
  const search = useDebounce(searchInput, 400)
  const [selectedLogId, setSelectedLogId] = useState<number | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const queryClient = useQueryClient()

  const handleRowClick = (logId: number) => {
    setSelectedLogId(logId)
    setDialogOpen(true)
  }

  // Reset page on filter change
  useEffect(() => { setPage(1) }, [statusFilter, clientFilter, search, dateFrom, dateTo])

  // Fetch clients for dropdown
  const { data: clientsData } = useQuery({
    queryKey: ["clients-dropdown"],
    queryFn: async () => {
      const res = await api.get<PaginatedResponse<Client>>("/clients", { params: { per_page: 200 } })
      return res.data.items
    },
    staleTime: 60_000,
  })

  // Fetch logs
  const { data: logsData, isLoading } = useQuery({
    queryKey: ["logs", page, statusFilter, clientFilter, search, dateFrom, dateTo],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, per_page: 20 }
      if (statusFilter !== "all") params.status = statusFilter
      if (clientFilter !== "all") params.client_id = clientFilter
      if (search) params.search = search
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      const res = await api.get<PaginatedResponse<TaskLogEntry>>("/logs", { params })
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.LOGS,
  })

  const handleExport = () => {
    const params = new URLSearchParams()
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (clientFilter !== "all") params.set("client_id", clientFilter)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    window.open(`/api/logs/export?${params.toString()}`, "_blank")
  }

  return (
    <div className="min-w-0">
      <PageHeader title="Logs de Execucao" description={logsData ? `${logsData.total} registros encontrados` : "Carregando..."}>
        <Button variant="outline" size="sm" onClick={handleExport}>
          <Download className="mr-1.5 h-4 w-4" />
          Exportar CSV
        </Button>
      </PageHeader>

      {/* Filters */}
      <Card className="mb-5">
        <CardContent className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="mb-1 block text-[11px] font-medium text-muted-foreground">Cliente</label>
            <Select value={clientFilter} onValueChange={setClientFilter}>
              <SelectTrigger className="h-9"><SelectValue placeholder="Todos" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {clientsData?.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.nome}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium text-muted-foreground">Status</label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-9"><SelectValue placeholder="Todos" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="success">Enviado</SelectItem>
                <SelectItem value="error">Erro</SelectItem>
                <SelectItem value="group">Grupo</SelectItem>
                <SelectItem value="not_found">Nao encontrado</SelectItem>
                <SelectItem value="skipped">Pulado</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium text-muted-foreground">De</label>
            <Input type="date" className="h-9" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium text-muted-foreground">Ate</label>
            <Input type="date" className="h-9" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div className="sm:col-span-2 lg:col-span-1">
            <label className="mb-1 block text-[11px] font-medium text-muted-foreground">Buscar</label>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="h-9 pl-9" placeholder="Buscar tarefa..." value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Logs Table */}
      <Card className="mb-5">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : !logsData?.items.length ? (
          <EmptyState icon={Search} title="Nenhum log encontrado" description="Ajuste os filtros ou aguarde novas execucoes" />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[110px]">Data</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Tarefa</TableHead>
                  <TableHead className="hidden sm:table-cell">Disciplina</TableHead>
                  <TableHead className="w-[70px]">Formato</TableHead>
                  <TableHead className="w-[90px]">Status</TableHead>
                  <TableHead className="hidden sm:table-cell">Erro</TableHead>
                  <TableHead className="hidden sm:table-cell w-[50px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logsData.items.map((log) => (
                  <TableRow
                    key={log.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleRowClick(log.id)}
                  >
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDateTime(log.created_at)}</TableCell>
                    <TableCell className="font-medium">{log.client_name}</TableCell>
                    <TableCell className="max-w-[120px] sm:max-w-[250px] truncate">{log.task_name}</TableCell>
                    <TableCell className="hidden sm:table-cell text-xs">{log.discipline}</TableCell>
                    <TableCell>{log.format && <FormatBadge format={log.format} />}</TableCell>
                    <TableCell><StatusBadge status={log.status} /></TableCell>
                    <TableCell className="hidden sm:table-cell max-w-[180px] truncate text-xs text-destructive">{log.error_msg || "—"}</TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <Button variant="ghost" size="icon" className="h-7 w-7">
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {logsData && logsData.pages > 1 && (
        <div className="mb-6 flex items-center justify-center gap-0.5 sm:gap-1">
          <Button variant="outline" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            &lt;
          </Button>
          {Array.from({ length: Math.min(logsData.pages, 7) }).map((_, i) => {
            let p: number
            if (logsData.pages <= 7) {
              p = i + 1
            } else if (page <= 4) {
              p = i + 1
            } else if (page >= logsData.pages - 3) {
              p = logsData.pages - 6 + i
            } else {
              p = page - 3 + i
            }
            return (
              <Button
                key={p}
                variant={p === page ? "default" : "outline"}
                size="icon"
                className="h-8 w-8 text-xs"
                onClick={() => setPage(p)}
              >
                {p}
              </Button>
            )
          })}
          <Button variant="outline" size="icon" className="h-8 w-8" disabled={page >= logsData.pages} onClick={() => setPage(page + 1)}>
            &gt;
          </Button>
        </div>
      )}

      {/* Server Terminal */}
      <ServerTerminal />

      {/* Task Detail Dialog */}
      <ActivityDetailDialog
        logId={selectedLogId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onUndoSuccess={() => queryClient.invalidateQueries({ queryKey: ["logs"] })}
      />
    </div>
  )
}

// ============================================
// SERVER TERMINAL COMPONENT
// ============================================

function ServerTerminal() {
  const [lines, setLines] = useState<string[]>([])
  const [paused, setPaused] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const terminalRef = useRef<HTMLDivElement>(null)
  const sessionId = useRef(`session_${Date.now()}`)

  const fetchLogs = useCallback(async () => {
    if (paused) return
    try {
      const res = await api.get("/logs/worker", {
        params: { lines: 200 },
      })
      const newLines: string[] = res.data.lines || []
      // Substitui todas as linhas (arquivo completo)
      setLines(newLines.slice(-500))
    } catch {
      // Silently fail
    }
  }, [paused])

  useEffect(() => {
    fetchLogs()
    const interval = setInterval(fetchLogs, REFRESH_INTERVALS.SERVER_LOGS)
    return () => clearInterval(interval)
  }, [fetchLogs])

  useEffect(() => {
    if (autoScroll && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [lines, autoScroll])

  const clearTerminal = () => {
    setLines([])
    sessionId.current = `session_${Date.now()}`
  }

  const colorize = (line: string) => {
    // Timestamp
    let colored = line.replace(
      /(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/g,
      '<span class="text-green-500/80">$1</span>'
    )
    // Log levels
    colored = colored.replace(/\bINFO\b/g, '<span class="text-sky-400">INFO</span>')
    colored = colored.replace(/\bWARNING\b/g, '<span class="text-yellow-400">WARNING</span>')
    colored = colored.replace(/\bERROR\b/g, '<span class="text-red-400">ERROR</span>')
    colored = colored.replace(/\bSUCCESS\b/g, '<span class="text-emerald-400">SUCCESS</span>')
    colored = colored.replace(/\bDEBUG\b/g, '<span class="text-zinc-500">DEBUG</span>')
    // Client tags
    colored = colored.replace(/\[([^\]]+)\]/g, '<span class="text-amber-600/80">[$1]</span>')
    return colored
  }

  return (
    <div>
      {/* Terminal Header */}
      <div className="flex items-center justify-between rounded-t-lg border border-b-0 border-border bg-zinc-900 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
            <span className="h-2.5 w-2.5 rounded-full bg-yellow-500" />
            <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
          </div>
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-300">
            <Terminal className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Logs do Worker (Celery)</span>
            <span className="sm:hidden">Worker</span>
          </div>
          <Badge variant="outline" className="hidden sm:inline-flex h-5 border-emerald-500/30 bg-emerald-500/10 px-1.5 text-[10px] text-emerald-400">
            <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
            Live
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200" onClick={() => setPaused(!paused)}>
            {paused ? <Play className="h-3 w-3 sm:mr-1" /> : <Pause className="h-3 w-3 sm:mr-1" />}
            <span className="hidden sm:inline">{paused ? "Retomar" : "Pausar"}</span>
          </Button>
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-zinc-400 hover:text-zinc-200" onClick={clearTerminal}>
            <Trash2 className="h-3 w-3 sm:mr-1" />
            <span className="hidden sm:inline">Limpar</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className={cn("h-7 px-2 text-xs", autoScroll ? "text-emerald-400" : "text-zinc-400 hover:text-zinc-200")}
            onClick={() => setAutoScroll(!autoScroll)}
          >
            <ArrowDown className="h-3 w-3 sm:mr-1" />
            <span className="hidden sm:inline">Auto-scroll</span>
          </Button>
        </div>
      </div>

      {/* Terminal Body */}
      <div
        ref={terminalRef}
        className="max-h-[200px] sm:max-h-[350px] overflow-y-auto rounded-b-lg border border-border bg-[#0a0a0c] p-4 font-mono text-xs leading-relaxed text-zinc-400"
        style={{ scrollbarWidth: "thin", scrollbarColor: "#27272a #0a0a0c" }}
      >
        {lines.length === 0 ? (
          <div className="py-8 text-center text-zinc-600">
            {paused ? "Terminal pausado" : "Aguardando logs do servidor..."}
          </div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all" dangerouslySetInnerHTML={{ __html: colorize(line) }} />
          ))
        )}
      </div>

      {/* Terminal Footer */}
      <div className="mt-0 flex items-center justify-between rounded-b-none border-x border-b border-border bg-zinc-900 px-4 py-1.5 text-[10px] text-zinc-500 rounded-b-lg" style={{ marginTop: "-1px" }}>
        <span>{lines.length} linhas</span>
        <span>Refresh: {REFRESH_INTERVALS.SERVER_LOGS / 1000}s {paused && "| PAUSADO"}</span>
      </div>
    </div>
  )
}
