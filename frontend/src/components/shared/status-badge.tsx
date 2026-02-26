import { Badge } from "@/components/ui/badge"

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; className: string }> = {
  active: { label: "Ativo", variant: "default", className: "bg-emerald-500/15 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/15" },
  running: { label: "Rodando", variant: "default", className: "bg-emerald-500/15 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/15" },
  paused: { label: "Pausado", variant: "default", className: "bg-amber-500/15 text-amber-500 border-amber-500/20 hover:bg-amber-500/15" },
  expired: { label: "Expirado", variant: "default", className: "bg-red-500/15 text-red-500 border-red-500/20 hover:bg-red-500/15" },
  idle: { label: "Ocioso", variant: "default", className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20 hover:bg-zinc-500/15" },
  error: { label: "Erro", variant: "default", className: "bg-red-500/15 text-red-500 border-red-500/20 hover:bg-red-500/15" },
  success: { label: "Enviado", variant: "default", className: "bg-emerald-500/15 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/15" },
  not_found: { label: "Nao encontrado", variant: "default", className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20 hover:bg-zinc-500/15" },
  group: { label: "Grupo", variant: "default", className: "bg-purple-500/15 text-purple-400 border-purple-500/20 hover:bg-purple-500/15" },
  skipped: { label: "Pulado", variant: "default", className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20 hover:bg-zinc-500/15" },
}

interface StatusBadgeProps {
  status: string
  showDot?: boolean
}

export function StatusBadge({ status, showDot = true }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.idle
  const dotColor = config.className.includes("emerald") ? "bg-emerald-500" :
    config.className.includes("amber") ? "bg-amber-500" :
    config.className.includes("red") ? "bg-red-500" :
    config.className.includes("purple") ? "bg-purple-400" : "bg-zinc-400"

  return (
    <Badge variant={config.variant} className={config.className}>
      {showDot && <span className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${dotColor}`} />}
      {config.label}
    </Badge>
  )
}
