import { NavLink } from "react-router-dom"
import { LayoutDashboard, Users, FileText, UserPlus, LogOut } from "lucide-react"
import { cn } from "@/lib/utils"
import { useLogout } from "@/hooks/use-auth"
import { useAuthStore } from "@/stores/auth-store"

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/clients", icon: Users, label: "Clientes" },
  { to: "/logs", icon: FileText, label: "Logs" },
]

export function Sidebar() {
  const logout = useLogout()
  const user = useAuthStore((s) => s.user)

  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex w-[220px] flex-col border-r border-border bg-card">
      {/* Brand */}
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 text-sm font-bold text-white">
          TS
        </div>
        <div>
          <div className="text-sm font-semibold">Teams Solver</div>
          <div className="text-[11px] text-muted-foreground">Painel Admin</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 px-2 py-3">
        <div className="mb-1 px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Menu
        </div>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
                isActive
                  ? "bg-indigo-500/10 text-indigo-400"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )
            }
          >
            <item.icon className="h-[18px] w-[18px]" />
            {item.label}
          </NavLink>
        ))}

        <div className="mb-1 mt-6 px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Sistema
        </div>
        <NavLink
          to="/clients/new"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
              isActive
                ? "bg-indigo-500/10 text-indigo-400"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )
          }
        >
          <UserPlus className="h-[18px] w-[18px]" />
          Novo Cliente
        </NavLink>
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-2">
        <div className="flex items-center gap-2.5 rounded-md px-3 py-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 text-xs font-semibold text-white">
            {user?.username?.[0]?.toUpperCase() || "A"}
          </div>
          <div className="flex-1 min-w-0">
            <div className="truncate text-[13px] font-medium">{user?.username || "Admin"}</div>
            <div className="text-[11px] text-muted-foreground">Administrador</div>
          </div>
          <button onClick={logout} className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors" title="Sair">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  )
}
