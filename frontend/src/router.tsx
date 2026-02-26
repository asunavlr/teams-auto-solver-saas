import { createBrowserRouter } from "react-router-dom"
import { AppLayout } from "@/components/layout/app-layout"
import { LoginPage } from "@/pages/login"
import { DashboardPage } from "@/pages/dashboard"
import { ClientsListPage } from "@/pages/clients-list"
import { ClientCreatePage } from "@/pages/client-create"
import { ClientEditPage } from "@/pages/client-edit"
import { ClientDetailPage } from "@/pages/client-detail"
import { LogsPage } from "@/pages/logs"
import { FinanceiroPage } from "@/pages/financeiro"

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/clients", element: <ClientsListPage /> },
      { path: "/clients/new", element: <ClientCreatePage /> },
      { path: "/clients/:id", element: <ClientDetailPage /> },
      { path: "/clients/:id/edit", element: <ClientEditPage /> },
      { path: "/logs", element: <LogsPage /> },
      { path: "/financeiro", element: <FinanceiroPage /> },
    ],
  },
], {
  basename: "/app",
})
