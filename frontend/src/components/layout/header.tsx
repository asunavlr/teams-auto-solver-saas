import { Moon, Sun, Bell } from "lucide-react"
import { useThemeStore } from "@/stores/theme-store"
import { Button } from "@/components/ui/button"

export function Header() {
  const { theme, setTheme } = useThemeStore()

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark")
  }

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-xl">
      <div />
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={toggleTheme} title="Alternar tema">
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button variant="outline" size="icon" className="h-8 w-8" title="Notificacoes">
          <Bell className="h-4 w-4" />
        </Button>
      </div>
    </header>
  )
}
