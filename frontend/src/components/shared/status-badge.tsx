import { Badge } from "@/components/ui/badge"

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; className: string }> = {
  active: { label: "Ativo", variant: "default", className: "bg-emerald-500/15 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/15" },
  running: { label: "Rodando", variant: "default", className: "bg-emerald-500/15 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/15" },
  paused: { label: "Pausado", variant: "default", className: "bg-amber-500/15 text-amber-500 border-amber-500/20 hover:bg-amber-500/15" },
  expired: { label: "Expirado", variant: "default", className: "bg-red-500/15 text-red-500 border-red-500/20 hover:bg-red-500/15" },
  idle: { label: "Ocioso", variant: "default", className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20 hover:bg-zinc-500/15" },
  error: { label: "Erro", variant: "default", className: "bg-red-500/15 text-red-500 border-red-500/20 hover:bg-red-500/15" },
  success: { label: "Enviado", variant: "default", className: "bg-emerald-500/15 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/15" },
  success_flagged: { label: "Enviado (revisar)", variant: "default", className: "bg-amber-500/15 text-amber-500 border-amber-500/20 hover:bg-amber-500/15" },
  not_found: { label: "Nao encontrado", variant: "default", className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20 hover:bg-zinc-500/15" },
  group: { label: "Grupo", variant: "default", className: "bg-purple-500/15 text-purple-400 border-purple-500/20 hover:bg-purple-500/15" },
  skipped: { label: "Pulado", variant: "default", className: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20 hover:bg-zinc-500/15" },
  undone: { label: "Desfeito", variant: "default", className: "bg-orange-500/15 text-orange-400 border-orange-500/20 hover:bg-orange-500/15" },
  // Novos status de analise de intencao
  skipped_announcement: { label: "Aviso", variant: "default", className: "bg-blue-500/15 text-blue-400 border-blue-500/20 hover:bg-blue-500/15" },
  skipped_personal: { label: "Pessoal", variant: "default", className: "bg-pink-500/15 text-pink-400 border-pink-500/20 hover:bg-pink-500/15" },
  skipped_certificate: { label: "Certificado", variant: "default", className: "bg-cyan-500/15 text-cyan-400 border-cyan-500/20 hover:bg-cyan-500/15" },
  skipped_group: { label: "Grupo", variant: "default", className: "bg-purple-500/15 text-purple-400 border-purple-500/20 hover:bg-purple-500/15" },
  skipped_external: { label: "Recurso externo", variant: "default", className: "bg-indigo-500/15 text-indigo-400 border-indigo-500/20 hover:bg-indigo-500/15" },
  skipped_presence: { label: "Presencial", variant: "default", className: "bg-teal-500/15 text-teal-400 border-teal-500/20 hover:bg-teal-500/15" },
  skipped_uncertain: { label: "Incerto", variant: "default", className: "bg-amber-500/15 text-amber-500 border-amber-500/20 hover:bg-amber-500/15" },
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
    config.className.includes("purple") ? "bg-purple-400" :
    config.className.includes("blue") ? "bg-blue-400" :
    config.className.includes("pink") ? "bg-pink-400" :
    config.className.includes("cyan") ? "bg-cyan-400" :
    config.className.includes("indigo") ? "bg-indigo-400" :
    config.className.includes("teal") ? "bg-teal-400" :
    config.className.includes("orange") ? "bg-orange-400" : "bg-zinc-400"

  return (
    <Badge variant={config.variant} className={config.className}>
      {showDot && <span className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${dotColor}`} />}
      {config.label}
    </Badge>
  )
}
