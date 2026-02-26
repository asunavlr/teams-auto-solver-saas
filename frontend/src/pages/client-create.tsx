import { useNavigate } from "react-router-dom"
import { useQuery, useMutation } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { motion } from "framer-motion"
import {
  ArrowLeft,
  User,
  KeyRound,
  CreditCard,
  Bell,
  Brain,
  Crown,
  Loader2,
} from "lucide-react"
import { toast } from "sonner"

import api from "@/lib/api"
import { formatCurrency } from "@/lib/utils"
import type { Plan } from "@/types/client"

import { PageHeader } from "@/components/shared/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
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

// ── Zod Schema ──
const clientCreateSchema = z.object({
  nome: z.string().min(1, "Nome e obrigatorio"),
  email: z.string().email("Email invalido"),
  teams_email: z.string().email("Email do Teams invalido"),
  teams_password: z.string().min(3, "Senha deve ter no minimo 3 caracteres"),
  anthropic_key: z.string().min(1, "Chave API Claude e obrigatoria"),
  plan_id: z.coerce.number().nullable(),
  check_interval: z.coerce.number().min(15, "Minimo 15 minutos").max(1440, "Maximo 1440 minutos"),
  months: z.coerce.number().min(1, "Minimo 1 mes").max(12, "Maximo 12 meses"),
  smtp_email: z.string().email("Email SMTP invalido").or(z.literal("")),
  smtp_password: z.string().optional().default(""),
  notification_email: z.string().email("Email de notificacao invalido").or(z.literal("")),
  whatsapp: z.string().optional().default(""),
  payment_amount: z.coerce.number().min(0, "Valor invalido").optional().default(0),
})

type ClientCreateFormValues = z.infer<typeof clientCreateSchema>

const sectionAnimation = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
}

export function ClientCreatePage() {
  const navigate = useNavigate()

  const form = useForm<ClientCreateFormValues>({
    resolver: zodResolver(clientCreateSchema) as any,
    defaultValues: {
      nome: "",
      email: "",
      teams_email: "",
      teams_password: "",
      anthropic_key: "",
      plan_id: null,
      check_interval: 60,
      months: 1,
      smtp_email: "",
      smtp_password: "",
      notification_email: "",
      whatsapp: "",
      payment_amount: 0,
    },
  })

  // ── Query: fetch plans ──
  const { data: plans = [] } = useQuery({
    queryKey: ["plans"],
    queryFn: async () => {
      const res = await api.get<Plan[]>("/plans")
      return res.data
    },
  })

  // ── Mutation: create client ──
  const create = useMutation({
    mutationFn: (data: ClientCreateFormValues) => api.post("/clients", data),
    onSuccess: (res) => {
      toast.success("Cliente criado com sucesso")
      const clientId = res.data?.id ?? res.data?.client?.id
      navigate(clientId ? `/clients/${clientId}` : "/clients")
    },
    onError: (err: unknown) => {
      const message =
        (err as { response?: { data?: { error?: string } } })?.response?.data
          ?.error ?? "Erro ao criar cliente"
      toast.error(message)
    },
  })

  function onSubmit(data: ClientCreateFormValues) {
    create.mutate(data)
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
        title="Novo Cliente"
        description="Preencha os dados para cadastrar"
      >
        <Button variant="ghost" size="sm" onClick={() => navigate("/clients")}>
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
                            placeholder="Senha de acesso"
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
                  <div className="grid grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="check_interval"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Intervalo (min)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              min={15}
                              max={1440}
                              {...field}
                            />
                          </FormControl>
                          <FormDescription className="text-[11px]">
                            15 a 1440 min
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="months"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Meses</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              min={1}
                              max={12}
                              {...field}
                            />
                          </FormControl>
                          <FormDescription className="text-[11px]">
                            1 a 12 meses
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
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
                            placeholder="sk-ant-..."
                            className="font-mono"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription className="text-[11px]">
                          Chave da API Anthropic (criptografada no banco)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </motion.div>

            {/* ── 5. Notificacoes ── */}
            <motion.div variants={sectionAnimation}>
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
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
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
                              placeholder="Senha do servidor"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
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
                </CardContent>
              </Card>
            </motion.div>

            {/* ── 6. Pagamento Inicial ── */}
            <motion.div variants={sectionAnimation}>
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-green-500/10">
                      <CreditCard className="h-4 w-4 text-green-500" />
                    </div>
                    <CardTitle className="text-sm">
                      Pagamento Inicial
                    </CardTitle>
                    <Badge
                      variant="outline"
                      className="ml-auto text-[10px] text-muted-foreground"
                    >
                      Opcional
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    Registre o valor recebido no momento do cadastro
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <FormField
                    control={form.control}
                    name="payment_amount"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Valor (R$)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={0}
                            step={0.01}
                            placeholder="0.00"
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
          </motion.div>

          {/* ── Footer ── */}
          <div className="flex items-center justify-end gap-3 border-t pt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate("/clients")}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : (
                "Salvar Cliente"
              )}
            </Button>
          </div>
        </form>
      </Form>
    </motion.div>
  )
}
