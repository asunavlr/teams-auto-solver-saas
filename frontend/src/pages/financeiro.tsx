import { useQuery } from "@tanstack/react-query"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts"
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Users,
  CreditCard,
  Percent,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react"

import { PageHeader } from "@/components/shared/page-header"
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
import api from "@/lib/api"
import { formatCurrency } from "@/lib/utils"
import { REFRESH_INTERVALS } from "@/lib/constants"

// Types
interface Resumo {
  receita: { mes: number; total: number }
  custos: { mes: number; total: number }
  lucro: { mes: number; total: number }
  clientes: { total: number; ativos: number; expirados: number; pausados: number }
  clientes_por_plano: { plano: string; preco: number; quantidade: number; receita_potencial: number }[]
  tarefas: { mes: number; sucesso: number }
  margem_lucro: number
}

interface ClienteFinanceiro {
  id: number
  nome: string
  email: string
  plano: string
  preco_plano: number
  status: string
  dias_restantes: number
  expires_at: string | null
  pagamentos_total: number
  ultimo_pagamento: string | null
  ultimo_valor: number
  custos_mes: number
  custos_total: number
  lucro_estimado: number
  tarefas_total: number
  tarefas_sucesso: number
  taxa_sucesso: number
  created_at: string | null
}

interface ReceitaMensal {
  mes: string
  receita: number
  custos: number
  lucro: number
}

const COLORS = ["#10b981", "#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444"]

export function FinanceiroPage() {
  const { data: resumo, isLoading: loadingResumo } = useQuery({
    queryKey: ["financeiro-resumo"],
    queryFn: async () => {
      const res = await api.get<Resumo>("/financeiro/resumo")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.DASHBOARD_STATS,
  })

  const { data: clientes, isLoading: loadingClientes } = useQuery({
    queryKey: ["financeiro-clientes"],
    queryFn: async () => {
      const res = await api.get<ClienteFinanceiro[]>("/financeiro/clientes")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.DASHBOARD_STATS,
  })

  const { data: receitaMensal } = useQuery({
    queryKey: ["financeiro-receita-mensal"],
    queryFn: async () => {
      const res = await api.get<ReceitaMensal[]>("/financeiro/receita-mensal")
      return res.data
    },
    refetchInterval: REFRESH_INTERVALS.DASHBOARD_STATS,
  })

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "ativo":
        return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Ativo</Badge>
      case "expirado":
        return <Badge className="bg-red-500/10 text-red-500 border-red-500/20">Expirado</Badge>
      case "pausado":
        return <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20">Pausado</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  return (
    <div>
      <PageHeader
        title="Financeiro"
        description="Visao geral de receitas, custos e lucros"
      />

      {/* Cards de Resumo */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
        {loadingResumo ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))
        ) : resumo ? (
          <>
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Receita do Mes</p>
                    <p className="text-2xl font-bold text-emerald-500">
                      {formatCurrency(resumo.receita.mes)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Total: {formatCurrency(resumo.receita.total)}
                    </p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-emerald-500/10 flex items-center justify-center">
                    <DollarSign className="h-6 w-6 text-emerald-500" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Custos do Mes</p>
                    <p className="text-2xl font-bold text-red-500">
                      {formatCurrency(resumo.custos.mes)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Total: {formatCurrency(resumo.custos.total)}
                    </p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-red-500/10 flex items-center justify-center">
                    <TrendingDown className="h-6 w-6 text-red-500" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Lucro do Mes</p>
                    <p className="text-2xl font-bold text-blue-500">
                      {formatCurrency(resumo.lucro.mes)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Total: {formatCurrency(resumo.lucro.total)}
                    </p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-blue-500/10 flex items-center justify-center">
                    <TrendingUp className="h-6 w-6 text-blue-500" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Margem de Lucro</p>
                    <p className="text-2xl font-bold text-purple-500">
                      {resumo.margem_lucro}%
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {resumo.clientes.ativos} clientes ativos
                    </p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-purple-500/10 flex items-center justify-center">
                    <Percent className="h-6 w-6 text-purple-500" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>

      {/* Graficos */}
      <div className="grid gap-6 md:grid-cols-2 mb-6">
        {/* Receita Mensal */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Receita vs Custos (6 meses)</CardTitle>
          </CardHeader>
          <CardContent>
            {receitaMensal ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={receitaMensal}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="mes" className="text-xs" />
                  <YAxis className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                    formatter={(value) => formatCurrency(Number(value) || 0)}
                  />
                  <Legend />
                  <Bar dataKey="receita" name="Receita" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="custos" name="Custos" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Skeleton className="h-[250px] w-full" />
            )}
          </CardContent>
        </Card>

        {/* Clientes por Plano */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Clientes por Plano</CardTitle>
          </CardHeader>
          <CardContent>
            {resumo?.clientes_por_plano ? (
              <div className="flex items-center gap-4">
                <ResponsiveContainer width="50%" height={200}>
                  <PieChart>
                    <Pie
                      data={resumo.clientes_por_plano.filter(p => p.quantidade > 0)}
                      dataKey="quantidade"
                      nameKey="plano"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ name, value }) => `${name}: ${value}`}
                    >
                      {resumo.clientes_por_plano.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `${value} clientes`} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-3 flex-1">
                  {resumo.clientes_por_plano.map((p, i) => (
                    <div key={p.plano} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-3 w-3 rounded-full"
                          style={{ backgroundColor: COLORS[i % COLORS.length] }}
                        />
                        <span className="text-sm">{p.plano}</span>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium">{p.quantidade} clientes</p>
                        <p className="text-xs text-muted-foreground">
                          {formatCurrency(p.receita_potencial)}/mes
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <Skeleton className="h-[200px] w-full" />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabela de Clientes */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-4 w-4" />
            Clientes - Detalhes Financeiros
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadingClientes ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : clientes && clientes.length > 0 ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Plano</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Preco</TableHead>
                    <TableHead className="text-right">Custos/Mes</TableHead>
                    <TableHead className="text-right">Lucro Est.</TableHead>
                    <TableHead className="text-right">Tarefas</TableHead>
                    <TableHead>Renovacao</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {clientes.map((cliente) => (
                    <TableRow key={cliente.id}>
                      <TableCell>
                        <div>
                          <p className="font-medium">{cliente.nome}</p>
                          <p className="text-xs text-muted-foreground">{cliente.email}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{cliente.plano}</Badge>
                      </TableCell>
                      <TableCell>{getStatusBadge(cliente.status)}</TableCell>
                      <TableCell className="text-right font-medium">
                        {formatCurrency(cliente.preco_plano)}
                      </TableCell>
                      <TableCell className="text-right text-red-500">
                        {formatCurrency(cliente.custos_mes)}
                      </TableCell>
                      <TableCell className={`text-right font-medium ${cliente.lucro_estimado >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                        {formatCurrency(cliente.lucro_estimado)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                          <span className="text-xs">{cliente.tarefas_sucesso}/{cliente.tarefas_total}</span>
                          <span className="text-xs text-muted-foreground">({cliente.taxa_sucesso}%)</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {cliente.status === "ativo" ? (
                          <div className="flex items-center gap-1">
                            <Clock className="h-3 w-3 text-muted-foreground" />
                            <span className="text-xs">{cliente.dias_restantes}d</span>
                          </div>
                        ) : cliente.status === "expirado" ? (
                          <span className="text-xs text-red-500">Expirado</span>
                        ) : (
                          <span className="text-xs text-yellow-500">Pausado</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Nenhum cliente encontrado
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resumo de Status */}
      {resumo && (
        <div className="grid gap-4 md:grid-cols-4 mt-6">
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
                <CheckCircle2 className="h-5 w-5 text-emerald-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{resumo.clientes.ativos}</p>
                <p className="text-xs text-muted-foreground">Clientes Ativos</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-red-500/10 flex items-center justify-center">
                <XCircle className="h-5 w-5 text-red-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{resumo.clientes.expirados}</p>
                <p className="text-xs text-muted-foreground">Expirados</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-yellow-500/10 flex items-center justify-center">
                <Clock className="h-5 w-5 text-yellow-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{resumo.clientes.pausados}</p>
                <p className="text-xs text-muted-foreground">Pausados</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center">
                <CreditCard className="h-5 w-5 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{resumo.tarefas.mes}</p>
                <p className="text-xs text-muted-foreground">Tarefas no Mes</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
