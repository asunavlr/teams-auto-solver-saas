import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { motion } from "framer-motion"
import {
  ArrowLeft,
  User,
  KeyRound,
  Bell,
  Brain,
  Crown,
  Loader2,
} from "lucide-react"
import { toast } from "sonner"

import api from "@/lib/api"
import { formatCurrency } from "@/lib/utils"
import type { Client, Plan } from "@/types/client"

import { PageHeader } from "@/components/shared/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from "@/components/ui/form"

// ── Zod Schema (edit: passwords are optional) ──
const clientEditSchema = z.object({
  nome: z.string().min(1, "Nome e obrigatorio"),
  email: z.string().email("Email invalido"),
  teams_email: z.string().email("Email do Teams invalido"),
  teams_password: z.string().optional().default(""),
  anthropic_key: z.string().optional().default(""),
  plan_id: z.coerce.number().nullable(),
  check_interval: z.coerce.number().min(15, "Minimo 15 minutos").max(1440, "Maximo 1440 minutos"),
  smtp_email: z.string().email("Email SMTP invalido").or(z.literal("")),
  smtp_password: z.string().optional().default(""),
  notification_email: z.string().email("Email de notificacao invalido").or(z.literal("")),
  whatsapp: z.string().optional().default(""),
})

type ClientEditFormValues = z.infer<typeof clientEditSchema>

const sectionAnimation = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
}

export function ClientEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // ── Query: fetch client data ──
  const { data: client, isLoading: clientLoading } = useQuery({
    queryKey: ["client", id],
    queryFn: async () => {
      const res = await api.get<Client>(`/clients/${id}?include_logs=true`)
      return res.data
    },
    enabled: !!id,
  })

  // ── Query: fetch plans ──
  const { data: plans = [] } = useQuery({
    queryKey: ["plans"],
    queryFn: async () => {
      const res = await api.get<Plan[]>("/plans")
      return res.data
    },
  })

  const form = useForm<ClientEditFormValues>({
    resolver: zodResolver(clientEditSchema) as any,
    values: client
      ? {
          nome: client.nome,
          email: client.email,
          teams_email: client.teams_email,
          teams_password: "",
          anthropic_key: "",
          plan_id: client.plan_id,
          check_interval: client.check_interval,
          smtp_email: client.smtp_email ?? "",
          smtp_password: "",
          notification_email: client.notification_email ?? "",
          whatsapp: client.whatsapp ?? "",
        }
      : undefined,
  })

  // ── Mutation: update client ──
  const update = useMutation({
    mutationFn: (data: ClientEditFormValues) => {
      // Only include password fields if they have values
      const payload: Record<string, unknown> = { ...data }
      if (!data.teams_password) delete payload.teams_password
      if (!data.anthropic_key) delete payload.anthropic_key
      if (!data.smtp_password) delete payload.smtp_password
      return api.put(`/clients/${id}`, payload)
    },
    onSuccess: () => {
      toast.success("Cliente atualizado com sucesso")
      queryClient.invalidateQueries({ queryKey: ["client", id] })
      queryClient.invalidateQueries({ queryKey: ["clients"] })
      navigate(`/clients/${id}`)
    },
    onError: (err: unknown) => {
      const message =
        (err as { response?: { data?: { error?: string } } })?.response?.data
          ?.error ?? "Erro ao atualizar cliente"
      toast.error(message)
    },
  })

  function onSubmit(data: ClientEditFormValues) {
    update.mutate(data)
  }

  if (clientLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-8 w-48" />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-xl" />
          ))}
        </div>
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* ── Header ── */}
      <PageHeader
        title={`Editar: ${client.nome}`}
        description="Atualize os dados do cliente"
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/clients/${id}`)}
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar
        </Button>
      </PageHeader>

      {/* ── Form ── */}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <motion.div
            initial="hidden"
            animate="show"
            transition={{ staggerChildren: 0.06 }}
            className="grid gap-6 lg:grid-cols-2"
          >
            {/* ── 1. Dados do Cliente ── */}
            <motion.div variants={sectionAnimation}>
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10">
                      <User className="h-4 w-4 text-indigo-500" />
                    </div>
                    <CardTitle className="text-sm">Dados do Cliente</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="nome"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Nome</FormLabel>
                        <FormControl>
                          <Input placeholder="Nome completo" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="email"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Email</FormLabel>
                        <FormControl>
                          <Input
                            type="email"
                            placeholder="cliente@email.com"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </motion.div>

            {/* ── 2. Credenciais Teams ── */}
            <motion.div variants={sectionAnimation}>
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-500/10">
                      <KeyRound className="h-4 w-4 text-purple-500" />
                    </div>
                    <CardTitle className="text-sm">Credenciais Teams</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="teams_email"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Email do Teams</FormLabel>
                        <FormControl>
                          <Input
                            type="email"
                            placeholder="aluno@instituicao.edu.br"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="teams_password"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Senha do Teams</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder="Deixe em branco para manter"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription className="text-[11px]">
                          Deixe em branco para manter a senha atual
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </motion.div>

            {/* ── 3. Plano e Assinatura ── */}
            <motion.div variants={sectionAnimation}>
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10">
                      <Crown className="h-4 w-4 text-emerald-500" />
                    </div>
                    <CardTitle className="text-sm">
                      Plano e Assinatura
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="plan_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Plano</FormLabel>
                        <Select
                          value={field.value?.toString() ?? ""}
                          onValueChange={(v) =>
                            field.onChange(v ? Number(v) : null)
                          }
                        >
                          <FormControl>
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder="Selecione um plano" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {plans.map((plan) => (
                              <SelectItem
                                key={plan.id}
                                value={plan.id.toString()}
                              >
                                {plan.nome} -{" "}
                                {formatCurrency(plan.preco_mensal)}/mes
                                {plan.limite_tarefas
                                  ? ` (${plan.limite_tarefas} tarefas)`
                                  : " (Ilimitado)"}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="check_interval"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Intervalo de Verificacao (min)</FormLabel>
                        <FormControl>
                          <Input type="number" min={15} max={1440} {...field} />
                        </FormControl>
                        <FormDescription className="text-[11px]">
                          15 a 1440 minutos
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </motion.div>

            {/* ── 4. Chave API Claude ── */}
            <motion.div variants={sectionAnimation}>
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10">
                      <Brain className="h-4 w-4 text-cyan-500" />
                    </div>
                    <CardTitle className="text-sm">Chave API Claude</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <FormField
                    control={form.control}
                    name="anthropic_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>API Key</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder="Deixe em branco para manter"
                            className="font-mono"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription className="text-[11px]">
                          Deixe em branco para manter a chave atual
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </motion.div>

            {/* ── 5. Notificacoes ── */}
            <motion.div variants={sectionAnimation} className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10">
                      <Bell className="h-4 w-4 text-amber-500" />
                    </div>
                    <CardTitle className="text-sm">Notificacoes</CardTitle>
                    <Badge
                      variant="outline"
                      className="ml-auto text-[10px] text-muted-foreground"
                    >
                      Opcional
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    Configure emails e WhatsApp para notificacoes
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="smtp_email"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Email SMTP</FormLabel>
                          <FormControl>
                            <Input
                              type="email"
                              placeholder="smtp@email.com"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="smtp_password"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Senha SMTP</FormLabel>
                          <FormControl>
                            <Input
                              type="password"
                              placeholder="Deixe em branco para manter"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="notification_email"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Email de Notificacao</FormLabel>
                          <FormControl>
                            <Input
                              type="email"
                              placeholder="notificacao@email.com"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="whatsapp"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>WhatsApp</FormLabel>
                          <FormControl>
                            <Input placeholder="5511999999999" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </motion.div>

          {/* ── Footer ── */}
          <div className="flex items-center justify-end gap-3 border-t pt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate(`/clients/${id}`)}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : (
                "Salvar Alteracoes"
              )}
            </Button>
          </div>
        </form>
      </Form>
    </motion.div>
  )
}
