import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { motion } from "framer-motion"
import {
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  Crown,
  DollarSign,
  Edit,
  FileCheck,
  Loader2,
  Mail,
  MessageSquare,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Timer,
  Trash2,
  X,
} from "lucide-react"
import { toast } from "sonner"

import api from "@/lib/api"
import { cn, formatCurrency, formatDate, formatDateTime, timeAgo } from "@/lib/utils"
import { REFRESH_INTERVALS } from "@/lib/constants"
import type { Client } from "@/types/client"

import { PageHeader } from "@/components/shared/page-header"
import { StatusBadge } from "@/components/shared/status-badge"
import { FormatBadge } from "@/components/shared/format-badge"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { ActivityDetailDialog } from "@/components/shared/activity-detail-dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

// ── Renew form schema ──
const renewSchema = z.object({
  months: z.coerce.number().min(1, "Minimo 1 mes").max(12, "Maximo 12 meses"),
  amount: z.coerce.number().min(0, "Valor invalido"),
})

// ── Payment form schema ──
const paymentSchema = z.object({
  amount: z.coerce.number().min(0.01, "Valor deve ser maior que zero"),
  months: z.coerce.number().min(1, "Minimo 1 mes").max(12, "Maximo 12 meses"),
})

type PaymentFormValues = z.infer<typeof paymentSchema>

type RenewFormValues = z.infer<typeof renewSchema>

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
}

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 },
}

export function ClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [renewOpen, setRenewOpen] = useState(false)
  const [paymentOpen, setPaymentOpen] = useState(false)
  const [editingPayment, setEditingPayment] = useState<{ id: number; amount: number; months: number } | null>(null)
  const [deletePaymentId, setDeletePaymentId] = useState<number | null>(null)
  const [selectedLogId, setSelectedLogId] = useState<number | null>(null)
  const [logDialogOpen, setLogDialogOpen] = useState(false)

  // ── Query: fetch client with logs + payments ──
  const { data: client, isLoading } = useQuery({
    queryKey: ["client", id],
    queryFn: async () => {
      const res = await api.get<Client>(`/clients/${id}?include_logs=true`)
      return res.data
    },
    enabled: !!id,
    refetchInterval: REFRESH_INTERVALS.CLIENTS_STATUS,
  })

  // ── Query: fetch processadas ──
  const { data: processadas } = useQuery({
    queryKey: ["processadas", id],
    queryFn: async () => {
      const res = await api.get<{ items: { id: string; nome: string; disciplina: string }[]; total: number }>(`/clients/${id}/processadas`)
      return res.data
    },
    enabled: !!id,
  })

  // ── Mutation: run now ──
  const run = useMutation({
    mutationFn: () => api.post(`/clients/${id}/run`),
    onSuccess: () => {
      toast.success("Execucao iniciada")
      queryClient.invalidateQueries({ queryKey: ["client", id] })
    },
    onError: () => toast.error("Erro ao iniciar execucao"),
  })

  // ── Mutation: toggle ──
  const toggle = useMutation({
    mutationFn: () => api.post(`/clients/${id}/toggle`),
    onSuccess: () => {
      toast.success("Status atualizado")
      queryClient.invalidateQueries({ queryKey: ["client", id] })
      queryClient.invalidateQueries({ queryKey: ["clients"] })
    },
    onError: () => toast.error("Erro ao alterar status"),
  })

  // ── Mutation: renew ──
  const renew = useMutation({
    mutationFn: (data: RenewFormValues) =>
      api.post(`/clients/${id}/renew`, data),
    onSuccess: () => {
      toast.success("Assinatura renovada com sucesso")
      setRenewOpen(false)
      queryClient.invalidateQueries({ queryKey: ["client", id] })
    },
    onError: () => toast.error("Erro ao renovar assinatura"),
  })

  // ── Mutation: add payment ──
  const addPayment = useMutation({
    mutationFn: (data: PaymentFormValues) =>
      api.post(`/financeiro/pagamentos`, { client_id: Number(id), ...data }),
    onSuccess: () => {
      toast.success("Pagamento registrado com sucesso")
      setPaymentOpen(false)
      queryClient.invalidateQueries({ queryKey: ["client", id] })
      queryClient.invalidateQueries({ queryKey: ["financeiro-resumo"] })
    },
    onError: () => toast.error("Erro ao registrar pagamento"),
  })

  // ── Mutation: edit payment ──
  const editPayment = useMutation({
    mutationFn: (data: PaymentFormValues & { id: number }) =>
      api.put(`/financeiro/pagamentos/${data.id}`, { amount: data.amount, months: data.months }),
    onSuccess: () => {
      toast.success("Pagamento atualizado")
      setEditingPayment(null)
      queryClient.invalidateQueries({ queryKey: ["client", id] })
      queryClient.invalidateQueries({ queryKey: ["financeiro-resumo"] })
    },
    onError: () => toast.error("Erro ao atualizar pagamento"),
  })

  // ── Mutation: delete payment ──
  const deletePayment = useMutation({
    mutationFn: (paymentId: number) => api.delete(`/financeiro/pagamentos/${paymentId}`),
    onSuccess: () => {
      toast.success("Pagamento excluido")
      setDeletePaymentId(null)
      queryClient.invalidateQueries({ queryKey: ["client", id] })
      queryClient.invalidateQueries({ queryKey: ["financeiro-resumo"] })
    },
    onError: () => toast.error("Erro ao excluir pagamento"),
  })

  // ── Mutation: delete processada ──
  const deleteProcessada = useMutation({
    mutationFn: (activityId: string) => api.delete(`/clients/${id}/processadas/${encodeURIComponent(activityId)}`),
    onSuccess: () => {
      toast.success("Atividade removida - pode ser reprocessada")
      queryClient.invalidateQueries({ queryKey: ["processadas", id] })
    },
    onError: () => toast.error("Erro ao remover atividade"),
  })

  // ── Mutation: clear all processadas ──
  const clearProcessadas = useMutation({
    mutationFn: () => api.delete(`/clients/${id}/processadas`),
    onSuccess: () => {
      toast.success("Todas atividades removidas")
      queryClient.invalidateQueries({ queryKey: ["processadas", id] })
    },
    onError: () => toast.error("Erro ao limpar atividades"),
  })

  // ── Mutation: delete ──
  const remove = useMutation({
    mutationFn: () => api.delete(`/clients/${id}`),
    onSuccess: () => {
      toast.success("Cliente excluido")
      navigate("/clients")
    },
    onError: () => toast.error("Erro ao excluir cliente"),
  })

  // ── Mutation: activate trial ──
  const activateTrial = useMutation({
    mutationFn: () => api.post(`/clients/${id}/trial`),
    onSuccess: () => {
      toast.success("Trial ativado com sucesso! 3 tarefas por 7 dias.")
      queryClient.invalidateQueries({ queryKey: ["client", id] })
      queryClient.invalidateQueries({ queryKey: ["clients"] })
    },
    onError: () => toast.error("Erro ao ativar trial"),
  })

  // ── Renew form ──
  const renewForm = useForm<RenewFormValues>({
    resolver: zodResolver(renewSchema) as any,
    defaultValues: { months: 1, amount: 0 },
  })

  // ── Payment form ──
  const paymentForm = useForm<PaymentFormValues>({
    resolver: zodResolver(paymentSchema) as any,
    defaultValues: { amount: 0, months: 1 },
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-72" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }

  if (!client) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        Cliente nao encontrado
      </div>
    )
  }

  const usagePercent = client.uso_percentual
  const taskLogs = client.task_logs ?? []
  const payments = client.payments ?? []

  // ── Stat cards data ──
  const statCards = [
    {
      label: "Tarefas Enviadas",
      value: client.tasks_completed,
      icon: CheckCircle2,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
    },
    {
      label: "Dias Restantes",
      value: client.days_remaining,
      icon: Calendar,
      color:
        client.days_remaining <= 3
          ? "text-red-500"
          : client.days_remaining <= 7
          ? "text-amber-500"
          : "text-emerald-500",
      bg:
        client.days_remaining <= 3
          ? "bg-red-500/10"
          : client.days_remaining <= 7
          ? "bg-amber-500/10"
          : "bg-emerald-500/10",
    },
    {
      label: "Intervalo",
      value: `${client.check_interval} min`,
      icon: Timer,
      color: "text-indigo-500",
      bg: "bg-indigo-500/10",
    },
    {
      label: "Expira em",
      value: client.expires_at ? formatDate(client.expires_at) : "N/A",
      icon: Clock,
      color: "text-zinc-400",
      bg: "bg-zinc-500/10",
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
        title={client.nome}
        description={`${client.email} — Cadastrado em ${client.created_at ? formatDate(client.created_at) : "N/A"}`}
      >
        <StatusBadge status={client.status} />
        <Button variant="ghost" size="sm" onClick={() => navigate("/clients")}>
          <ArrowLeft className="h-4 w-4" />
          Voltar
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
                <div
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-lg",
                    s.bg
                  )}
                >
                  <s.icon className={cn("h-4 w-4", s.color)} />
                </div>
                <div>
                  <p className="text-lg font-semibold tracking-tight">
                    {s.value}
                  </p>
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* ── Plan Usage Bar ── */}
      <motion.div variants={item} initial="hidden" animate="show">
        <Card className="py-4">
          <CardContent>
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-lg",
                  client.is_trial ? "bg-emerald-500/10" : "bg-indigo-500/10"
                )}>
                  <Crown className={cn("h-5 w-5", client.is_trial ? "text-emerald-500" : "text-indigo-500")} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">
                      {client.plan_name ?? "Sem plano"}
                    </p>
                    {client.is_trial && (
                      <Badge variant="secondary" className="text-[10px] bg-emerald-500/10 text-emerald-500">
                        Trial - 7 dias
                      </Badge>
                    )}
                  </div>
                  {client.plan_price != null && client.plan_price > 0 && (
                    <p className="text-xs text-muted-foreground">
                      {formatCurrency(client.plan_price)}/mes
                    </p>
                  )}
                  {client.is_trial && (
                    <p className="text-xs text-muted-foreground">
                      Gratuito - {client.limite_tarefas} tarefas
                    </p>
                  )}
                </div>
              </div>
              <div className="flex flex-1 items-center gap-3 max-w-md">
                <Progress
                  value={usagePercent}
                  className={cn(
                    "h-2",
                    usagePercent >= 90
                      ? "[&>[data-slot=progress-indicator]]:bg-red-500"
                      : usagePercent >= 70
                      ? "[&>[data-slot=progress-indicator]]:bg-amber-500"
                      : "[&>[data-slot=progress-indicator]]:bg-emerald-500"
                  )}
                />
                <span className="whitespace-nowrap text-sm text-muted-foreground">
                  {client.tarefas_mes} de{" "}
                  {client.limite_tarefas ?? "Ilimitadas"} tarefas
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* ── Action Bar ── */}
      <motion.div
        variants={item}
        initial="hidden"
        animate="show"
        className="flex flex-wrap items-center gap-2"
      >
        <Button variant="outline" size="sm" asChild>
          <Link to={`/clients/${id}/edit`}>
            <Edit className="h-4 w-4" />
            Editar
          </Link>
        </Button>

        <Button
          variant="outline"
          size="sm"
          disabled={run.isPending}
          onClick={() => run.mutate()}
        >
          {run.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Executar Agora
        </Button>

        <Button
          variant="outline"
          size="sm"
          disabled={toggle.isPending}
          onClick={() => toggle.mutate()}
        >
          {toggle.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : client.status === "active" ? (
            <Pause className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {client.status === "active" ? "Pausar" : "Ativar"}
        </Button>

        <Separator orientation="vertical" className="mx-1 h-6" />

        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            renewForm.reset({ months: 1, amount: 0 })
            setRenewOpen(true)
          }}
        >
          <RefreshCw className="h-4 w-4" />
          Renovar
        </Button>

        {client.can_use_trial && (
          <Button
            variant="outline"
            size="sm"
            className="text-emerald-500 hover:text-emerald-500 hover:bg-emerald-500/10"
            disabled={activateTrial.isPending}
            onClick={() => activateTrial.mutate()}
          >
            {activateTrial.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Ativar Trial
          </Button>
        )}

        <Button
          variant="outline"
          size="sm"
          className="text-red-500 hover:text-red-500 hover:bg-red-500/10"
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="h-4 w-4" />
          Excluir
        </Button>
      </motion.div>

      {/* ── Info + Payments Grid ── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Client Info */}
        <motion.div variants={item} initial="hidden" animate="show">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Informacoes do Cliente</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2">
                <DetailItem
                  icon={<Mail className="h-4 w-4 text-muted-foreground" />}
                  label="Email"
                  value={client.email}
                />
                <DetailItem
                  icon={<Mail className="h-4 w-4 text-indigo-500" />}
                  label="Email Teams"
                  value={client.teams_email}
                  mono
                />
                <DetailItem
                  icon={
                    <MessageSquare className="h-4 w-4 text-muted-foreground" />
                  }
                  label="Notificacao"
                  value={client.notification_email || "Nao configurado"}
                />
                <DetailItem
                  icon={<Clock className="h-4 w-4 text-muted-foreground" />}
                  label="Ultimo Check"
                  value={
                    client.last_check
                      ? timeAgo(client.last_check)
                      : "Nunca executado"
                  }
                />
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Payments History */}
        <motion.div variants={item} initial="hidden" animate="show">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-sm">
                Historico de Pagamentos
              </CardTitle>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  paymentForm.reset({ amount: client.plan_price || 0, months: 1 })
                  setPaymentOpen(true)
                }}
              >
                <Plus className="h-4 w-4" />
                Registrar
              </Button>
            </CardHeader>
            <CardContent className="p-0">
              {payments.length === 0 ? (
                <p className="px-6 pb-6 text-sm text-muted-foreground">
                  Nenhum pagamento registrado
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-6">Data</TableHead>
                      <TableHead>Meses</TableHead>
                      <TableHead className="text-right">Valor</TableHead>
                      <TableHead className="pr-6 w-[80px]"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {payments.map((payment) => (
                      <TableRow key={payment.id}>
                        <TableCell className="pl-6 text-sm">
                          {formatDate(payment.created_at)}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs">
                            {payment.months}{" "}
                            {payment.months === 1 ? "mes" : "meses"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-medium text-emerald-500">
                          {formatCurrency(payment.amount)}
                        </TableCell>
                        <TableCell className="pr-6">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => {
                                setEditingPayment({
                                  id: payment.id,
                                  amount: payment.amount,
                                  months: payment.months,
                                })
                              }}
                            >
                              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-red-500 hover:text-red-500 hover:bg-red-500/10"
                              onClick={() => setDeletePaymentId(payment.id)}
                            >
                              <X className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* ── Task History ── */}
      <motion.div variants={item} initial="hidden" animate="show">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Historico de Tarefas</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {taskLogs.length === 0 ? (
              <p className="px-6 pb-6 text-sm text-muted-foreground">
                Nenhuma tarefa processada ainda
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-6">Data</TableHead>
                    <TableHead>Tarefa</TableHead>
                    <TableHead>Disciplina</TableHead>
                    <TableHead>Formato</TableHead>
                    <TableHead className="pr-6">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {taskLogs.map((log) => (
                    <TableRow
                      key={log.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => {
                        setSelectedLogId(log.id)
                        setLogDialogOpen(true)
                      }}
                    >
                      <TableCell className="pl-6 text-sm text-muted-foreground">
                        {formatDateTime(log.created_at)}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-sm font-medium">
                        {log.task_name}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {log.discipline || "-"}
                      </TableCell>
                      <TableCell>
                        {log.format ? (
                          <FormatBadge format={log.format} />
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            -
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="pr-6">
                        <StatusBadge status={log.status} showDot={false} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* ── Processed Activities ── */}
      <motion.div variants={item} initial="hidden" animate="show">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <FileCheck className="h-4 w-4" />
              Atividades Processadas
            </CardTitle>
            {processadas && processadas.total > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="text-red-500 hover:text-red-500"
                onClick={() => clearProcessadas.mutate()}
                disabled={clearProcessadas.isPending}
              >
                {clearProcessadas.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Limpar Todas
              </Button>
            )}
          </CardHeader>
          <CardContent className="p-0">
            {!processadas || processadas.total === 0 ? (
              <p className="px-6 pb-6 text-sm text-muted-foreground">
                Nenhuma atividade processada
              </p>
            ) : (
              <div className="max-h-[300px] overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-6">Atividade</TableHead>
                      <TableHead>Disciplina</TableHead>
                      <TableHead className="pr-6 w-[100px]"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {processadas.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="pl-6">
                          <div>
                            <p className="text-sm font-medium">
                              {item.nome || <span className="text-muted-foreground italic">Sem nome</span>}
                            </p>
                            <code className="text-[10px] text-muted-foreground">
                              {item.id.substring(0, 12)}...
                            </code>
                          </div>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-muted-foreground">
                            {item.disciplina || "-"}
                          </span>
                        </TableCell>
                        <TableCell className="pr-6">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-500 hover:bg-red-500/10"
                            onClick={() => deleteProcessada.mutate(item.id)}
                            disabled={deleteProcessada.isPending}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            <div className="px-6 py-3 border-t text-xs text-muted-foreground">
              Total: {processadas?.total ?? 0} atividades processadas.
              Remova uma para que possa ser reprocessada.
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* ── Renew Dialog ── */}
      <Dialog open={renewOpen} onOpenChange={setRenewOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Renovar Assinatura</DialogTitle>
            <DialogDescription>
              Adicione meses a assinatura de {client.nome}
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={renewForm.handleSubmit((data) => renew.mutate(data))}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="renew-months">Meses</Label>
              <Input
                id="renew-months"
                type="number"
                min={1}
                max={12}
                {...renewForm.register("months", { valueAsNumber: true })}
              />
              {renewForm.formState.errors.months && (
                <p className="text-sm text-destructive">
                  {renewForm.formState.errors.months.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="renew-amount">Valor (R$)</Label>
              <Input
                id="renew-amount"
                type="number"
                min={0}
                step={0.01}
                {...renewForm.register("amount", { valueAsNumber: true })}
              />
              {renewForm.formState.errors.amount && (
                <p className="text-sm text-destructive">
                  {renewForm.formState.errors.amount.message}
                </p>
              )}
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setRenewOpen(false)}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={renew.isPending}>
                {renew.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Renovando...
                  </>
                ) : (
                  "Confirmar Renovacao"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Payment Dialog ── */}
      <Dialog open={paymentOpen} onOpenChange={setPaymentOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar Pagamento</DialogTitle>
            <DialogDescription>
              Registre um pagamento para {client.nome}
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={paymentForm.handleSubmit((data) => addPayment.mutate(data))}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="payment-amount">Valor (R$)</Label>
              <Input
                id="payment-amount"
                type="number"
                min={0.01}
                step={0.01}
                {...paymentForm.register("amount", { valueAsNumber: true })}
              />
              {paymentForm.formState.errors.amount && (
                <p className="text-sm text-destructive">
                  {paymentForm.formState.errors.amount.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="payment-months">Meses Referentes</Label>
              <Input
                id="payment-months"
                type="number"
                min={1}
                max={12}
                {...paymentForm.register("months", { valueAsNumber: true })}
              />
              {paymentForm.formState.errors.months && (
                <p className="text-sm text-destructive">
                  {paymentForm.formState.errors.months.message}
                </p>
              )}
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setPaymentOpen(false)}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={addPayment.isPending}>
                {addPayment.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Salvando...
                  </>
                ) : (
                  <>
                    <DollarSign className="h-4 w-4" />
                    Registrar
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Edit Payment Dialog ── */}
      <Dialog open={!!editingPayment} onOpenChange={(open) => !open && setEditingPayment(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Pagamento</DialogTitle>
            <DialogDescription>
              Altere os dados do pagamento
            </DialogDescription>
          </DialogHeader>
          {editingPayment && (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const formData = new FormData(e.currentTarget)
                editPayment.mutate({
                  id: editingPayment.id,
                  amount: Number(formData.get("edit-amount")),
                  months: Number(formData.get("edit-months")),
                })
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="edit-amount">Valor (R$)</Label>
                <Input
                  id="edit-amount"
                  name="edit-amount"
                  type="number"
                  min={0.01}
                  step={0.01}
                  defaultValue={editingPayment.amount}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-months">Meses Referentes</Label>
                <Input
                  id="edit-months"
                  name="edit-months"
                  type="number"
                  min={1}
                  max={12}
                  defaultValue={editingPayment.months}
                />
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingPayment(null)}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={editPayment.isPending}>
                  {editPayment.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Salvando...
                    </>
                  ) : (
                    "Salvar"
                  )}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Delete Payment Confirm Dialog ── */}
      <ConfirmDialog
        open={!!deletePaymentId}
        onOpenChange={(open) => !open && setDeletePaymentId(null)}
        title="Excluir Pagamento"
        description="Tem certeza que deseja excluir este pagamento? Esta acao e irreversivel."
        confirmLabel="Excluir"
        variant="destructive"
        onConfirm={() => deletePaymentId && deletePayment.mutate(deletePaymentId)}
      />

      {/* ── Delete Confirm Dialog ── */}
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Excluir Cliente"
        description={`Tem certeza que deseja excluir ${client.nome}? Esta acao e irreversivel e removera todos os dados, tarefas e pagamentos associados.`}
        confirmLabel="Excluir"
        variant="destructive"
        onConfirm={() => remove.mutate()}
      />

      {/* ── Activity Detail Dialog ── */}
      <ActivityDetailDialog
        logId={selectedLogId}
        open={logDialogOpen}
        onOpenChange={setLogDialogOpen}
        onUndoSuccess={() => queryClient.invalidateQueries({ queryKey: ["client", id] })}
      />
    </motion.div>
  )
}

// ── Detail Item sub-component ──
function DetailItem({
  icon,
  label,
  value,
  mono = false,
}: {
  icon: React.ReactNode
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="mt-0.5">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p
          className={cn(
            "truncate text-sm",
            mono && "font-mono text-xs"
          )}
        >
          {value}
        </p>
      </div>
    </div>
  )
}
