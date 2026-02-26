import { Navigate, Outlet } from "react-router-dom"
import { useAuthStore } from "@/stores/auth-store"
import { Sidebar } from "./sidebar"
import { Header } from "./header"

export function AppLayout() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-[220px]">
        <Header />
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
