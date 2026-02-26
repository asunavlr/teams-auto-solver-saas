import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Loader2, Lock, User } from "lucide-react"
import { motion } from "framer-motion"

import { useLogin } from "@/hooks/use-auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"

const loginSchema = z.object({
  username: z.string().min(1, "Usuario e obrigatorio"),
  password: z.string().min(3, "Senha deve ter no minimo 3 caracteres"),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const login = useLogin()

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: "",
      password: "",
    },
  })

  function onSubmit(data: LoginFormValues) {
    login.mutate(data)
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#09090b]">
      {/* Animated gradient orbs */}
      <div
        className="pointer-events-none absolute -left-32 -top-32 h-[500px] w-[500px] rounded-full opacity-30 blur-[120px]"
        style={{
          background: "radial-gradient(circle, #6366f1, transparent 70%)",
          animation: "float-orb-1 20s ease-in-out infinite",
        }}
      />
      <div
        className="pointer-events-none absolute -bottom-40 -right-20 h-[450px] w-[450px] rounded-full opacity-25 blur-[120px]"
        style={{
          background: "radial-gradient(circle, #8b5cf6, transparent 70%)",
          animation: "float-orb-2 25s ease-in-out infinite",
        }}
      />
      <div
        className="pointer-events-none absolute left-1/2 top-1/3 h-[400px] w-[400px] -translate-x-1/2 rounded-full opacity-20 blur-[120px]"
        style={{
          background: "radial-gradient(circle, #06b6d4, transparent 70%)",
          animation: "float-orb-3 18s ease-in-out infinite",
        }}
      />

      {/* Keyframes injected via style tag */}
      <style>{`
        @keyframes float-orb-1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          25% { transform: translate(80px, 40px) scale(1.1); }
          50% { transform: translate(30px, -60px) scale(0.95); }
          75% { transform: translate(-50px, 30px) scale(1.05); }
        }
        @keyframes float-orb-2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          25% { transform: translate(-60px, -50px) scale(1.08); }
          50% { transform: translate(40px, 30px) scale(0.92); }
          75% { transform: translate(20px, -40px) scale(1.03); }
        }
        @keyframes float-orb-3 {
          0%, 100% { transform: translate(-50%, 0) scale(1); }
          33% { transform: translate(calc(-50% + 70px), -50px) scale(1.12); }
          66% { transform: translate(calc(-50% - 40px), 40px) scale(0.9); }
        }
      `}</style>

      {/* Glassmorphism card */}
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.21, 0.47, 0.32, 0.98] }}
        className="relative z-10 w-full max-w-[400px] mx-4"
      >
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-8 shadow-2xl shadow-black/40 backdrop-blur-xl">
          {/* Logo and title */}
          <div className="mb-8 flex flex-col items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-cyan-500 shadow-lg shadow-indigo-500/25">
              <span className="text-xl font-bold tracking-tight text-white">TS</span>
            </div>
            <div className="text-center">
              <h1 className="text-xl font-semibold tracking-tight text-white">
                Teams Auto Solver
              </h1>
              <p className="mt-1 text-sm text-zinc-400">
                Painel de Administracao
              </p>
            </div>
          </div>

          {/* Form */}
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-zinc-300 text-xs font-medium uppercase tracking-wider">
                      Usuario
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                        <Input
                          placeholder="admin"
                          className="h-10 border-white/[0.08] bg-white/[0.04] pl-10 text-white placeholder:text-zinc-600 focus-visible:border-indigo-500/50 focus-visible:ring-indigo-500/20"
                          {...field}
                        />
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-zinc-300 text-xs font-medium uppercase tracking-wider">
                      Senha
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                        <Input
                          type="password"
                          placeholder="••••••"
                          className="h-10 border-white/[0.08] bg-white/[0.04] pl-10 text-white placeholder:text-zinc-600 focus-visible:border-indigo-500/50 focus-visible:ring-indigo-500/20"
                          {...field}
                        />
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button
                type="submit"
                disabled={login.isPending}
                className="h-10 w-full bg-gradient-to-r from-indigo-500 to-purple-600 font-medium text-white shadow-lg shadow-indigo-500/20 transition-all hover:from-indigo-600 hover:to-purple-700 hover:shadow-indigo-500/30 disabled:opacity-60"
              >
                {login.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Entrando...
                  </>
                ) : (
                  "Entrar"
                )}
              </Button>
            </form>
          </Form>

          {/* Subtle footer */}
          <p className="mt-6 text-center text-[11px] text-zinc-600">
            Acesso restrito a administradores
          </p>
        </div>
      </motion.div>
    </div>
  )
}
