import { cn } from "@/lib/utils"

const formatColors: Record<string, string> = {
  docx: "bg-blue-500/15 text-blue-400",
  xlsx: "bg-emerald-500/15 text-emerald-400",
  pptx: "bg-amber-500/15 text-amber-400",
  pdf: "bg-red-500/15 text-red-400",
  py: "bg-sky-500/15 text-sky-400",
  js: "bg-yellow-500/15 text-yellow-400",
  ts: "bg-blue-500/15 text-blue-400",
  java: "bg-orange-500/15 text-orange-400",
  c: "bg-zinc-500/15 text-zinc-400",
  cpp: "bg-zinc-500/15 text-zinc-400",
  html: "bg-purple-500/15 text-purple-400",
  css: "bg-pink-500/15 text-pink-400",
  sql: "bg-cyan-500/15 text-cyan-400",
  zip: "bg-amber-500/15 text-amber-400",
  txt: "bg-zinc-500/15 text-zinc-400",
  texto: "bg-zinc-500/15 text-zinc-400",
}

export function FormatBadge({ format }: { format: string }) {
  const fmt = format.toLowerCase().replace(".", "")
  const color = formatColors[fmt] || formatColors.txt
  return (
    <span className={cn("inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide", color)}>
      .{fmt}
    </span>
  )
}
