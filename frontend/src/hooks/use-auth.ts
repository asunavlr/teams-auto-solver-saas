import { useMutation } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import api from "@/lib/api"
import { useAuthStore } from "@/stores/auth-store"

export function useLogin() {
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async (data: { username: string; password: string }) => {
      const res = await api.post("/auth/login", data)
      return res.data
    },
    onSuccess: (data) => {
      setAuth(data.token, data.user)
      toast.success("Login realizado com sucesso")
      navigate("/")
    },
    onError: () => {
      toast.error("Usuario ou senha incorretos")
    },
  })
}

export function useLogout() {
  const { logout, token } = useAuthStore()
  const navigate = useNavigate()

  return () => {
    if (token) {
      api.post("/auth/logout").catch(() => {})
    }
    logout()
    navigate("/login")
  }
}
