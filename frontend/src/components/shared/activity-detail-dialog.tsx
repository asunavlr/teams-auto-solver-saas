import { useState, type ChangeEvent } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { FileText, MessageSquare, Files, Undo2, Loader2, Download, Upload, X } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { StatusBadge } from "@/components/shared/status-badge"
import { FormatBadge } from "@/components/shared/format-badge"
import api from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type { TaskLogEntry } from "@/types/client"

interface ActivityDetailDialogProps {
  logId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onUndoSuccess?: () => void
}

export function ActivityDetailDialog({
  logId,
  open,
  onOpenChange,
  onUndoSuccess,
}: ActivityDetailDialogProps) {
  const queryClient = useQueryClient()
  const [undoDialogOpen, setUndoDialogOpen] = useState(false)
  const [reprocessar, setReprocessar] = useState(false)
  const [resubmitDialogOpen, setResubmitDialogOpen] = useState(false)
  const [resubmitFiles, setResubmitFiles] = useState<File[]>([])

  const { data: logDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ["log-detail", logId],
    queryFn: async () => {
      if (!logId) return null
      const res = await api.get<TaskLogEntry>(`/logs/${logId}`)
      return res.data
    },
    enabled: !!logId && open,
  })

  const undoMutation = useMutation({
    mutationFn: async ({ logId, reprocessar }: { logId: number; reprocessar: boolean }) => {
      const res = await api.post(`/logs/${logId}/undo`, { reprocessar })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["log-detail", logId] })
      setUndoDialogOpen(false)
      onOpenChange(false)
      onUndoSuccess?.()
    },
  })

  const resubmitMutation = useMutation({
    mutationFn: async ({ logId, files }: { logId: number; files: File[] }) => {
      const formData = new FormData()
      files.forEach(file => formData.append("files", file))
      const res = await api.post(`/logs/${logId}/resubmit`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["log-detail", logId] })
      setResubmitDialogOpen(false)
      setResubmitFiles([])
      onOpenChange(false)
      onUndoSuccess?.()
    },
  })

  const handleUndoClick = () => {
    setReprocessar(false)
    setUndoDialogOpen(true)
  }

  const handleUndoConfirm = () => {
    if (logId) {
      undoMutation.mutate({ logId, reprocessar })
    }
  }

  const handleResubmitClick = () => {
    setResubmitFiles([])
    setResubmitDialogOpen(true)
  }

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setResubmitFiles(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  const handleRemoveFile = (index: number) => {
    setResubmitFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleResubmitConfirm = () => {
    if (logId && resubmitFiles.length > 0) {
      resubmitMutation.mutate({ logId, files: resubmitFiles })
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Detalhes da Atividade
            </DialogTitle>
            {logDetail && (
              <DialogDescription className="flex items-center gap-3 pt-2">
                <StatusBadge status={logDetail.status} />
                {logDetail.format && <FormatBadge format={logDetail.format} />}
                <span className="text-xs text-muted-foreground">{formatDateTime(logDetail.created_at)}</span>
              </DialogDescription>
            )}
          </DialogHeader>

          {loadingDetail ? (
            <div className="space-y-3 py-4">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : logDetail ? (
            <div className="space-y-4">
              {/* Task Info */}
              <div className="rounded-lg border p-4 space-y-2">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Cliente:</span>
                    <span className="ml-2 font-medium">{logDetail.client_name}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Disciplina:</span>
                    <span className="ml-2">{logDetail.discipline || "—"}</span>
                  </div>
                </div>
                <div className="text-sm">
                  <span className="text-muted-foreground">Tarefa:</span>
                  <span className="ml-2 font-medium">{logDetail.task_name}</span>
                </div>
                {logDetail.error_msg && (
                  <div className="text-sm text-destructive">
                    <span className="font-medium">Erro:</span>
                    <span className="ml-2">{logDetail.error_msg}</span>
                  </div>
                )}
              </div>

              {/* Tabs for Instructions and Response */}
              <Tabs defaultValue="instrucoes" className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="instrucoes" className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Instrucoes
                  </TabsTrigger>
                  <TabsTrigger value="resposta" className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4" />
                    Resposta Enviada
                  </TabsTrigger>
                  <TabsTrigger value="arquivos" className="flex items-center gap-2">
                    <Files className="h-4 w-4" />
                    Arquivos ({logDetail.arquivos_enviados?.length || 0})
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="instrucoes" className="mt-4">
                  <ScrollArea className="h-[200px] sm:h-[300px] rounded-md border p-4">
                    {logDetail.instrucoes ? (
                      <pre className="whitespace-pre-wrap text-sm font-mono">{logDetail.instrucoes}</pre>
                    ) : (
                      <div className="text-center text-muted-foreground py-8">
                        Sem instrucoes registradas
                      </div>
                    )}
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="resposta" className="mt-4">
                  <ScrollArea className="h-[200px] sm:h-[300px] rounded-md border p-4">
                    {logDetail.resposta ? (
                      <pre className="whitespace-pre-wrap text-sm font-mono">{logDetail.resposta}</pre>
                    ) : (
                      <div className="text-center text-muted-foreground py-8">
                        Sem resposta registrada
                      </div>
                    )}
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="arquivos" className="mt-4">
                  <ScrollArea className="h-[200px] sm:h-[300px] rounded-md border p-4">
                    {logDetail.arquivos_enviados && logDetail.arquivos_enviados.length > 0 ? (
                      <ul className="space-y-3">
                        {logDetail.arquivos_enviados.map((arquivo, idx) => {
                          const fileName = arquivo.split(/[/\\]/).pop() || arquivo
                          return (
                            <li key={idx} className="flex items-center justify-between gap-3 p-2 rounded-lg border bg-muted/30">
                              <div className="flex items-center gap-2 min-w-0">
                                <Files className="h-4 w-4 text-muted-foreground shrink-0" />
                                <span className="text-sm truncate" title={arquivo}>{fileName}</span>
                              </div>
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 shrink-0"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  window.open(`/api/logs/${logDetail.id}/files/${idx}`, "_blank")
                                }}
                              >
                                <Download className="h-3 w-3 mr-1" />
                                Baixar
                              </Button>
                            </li>
                          )
                        })}
                      </ul>
                    ) : (
                      <div className="text-center text-muted-foreground py-8">
                        Nenhum arquivo registrado
                      </div>
                    )}
                  </ScrollArea>
                </TabsContent>
              </Tabs>

              {/* Action Buttons */}
              {(logDetail.status === "success" || logDetail.status === "success_flagged") && (
                <div className="flex justify-end gap-2 pt-4 border-t">
                  <Button
                    variant="outline"
                    onClick={handleResubmitClick}
                    disabled={undoMutation.isPending || resubmitMutation.isPending}
                  >
                    <Upload className="mr-2 h-4 w-4" />
                    Reenviar com novo arquivo
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleUndoClick}
                    disabled={undoMutation.isPending || resubmitMutation.isPending}
                  >
                    <Undo2 className="mr-2 h-4 w-4" />
                    Desfazer Envio
                  </Button>
                </div>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Undo Confirmation Dialog */}
      <AlertDialog open={undoDialogOpen} onOpenChange={setUndoDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desfazer envio da tarefa?</AlertDialogTitle>
            <AlertDialogDescription>
              Isso vai abrir o navegador do cliente, acessar a tarefa no Teams e clicar em "Desfazer entrega".
              O processo pode levar alguns minutos.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="flex items-center space-x-3 py-4">
            <Switch
              id="reprocessar"
              checked={reprocessar}
              onCheckedChange={setReprocessar}
            />
            <Label htmlFor="reprocessar" className="text-sm">
              Reprocessar no proximo ciclo
            </Label>
          </div>
          <p className="text-xs text-muted-foreground -mt-2">
            Se marcado, a tarefa sera processada novamente automaticamente.
          </p>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={undoMutation.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleUndoConfirm}
              disabled={undoMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {undoMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processando...
                </>
              ) : (
                <>
                  <Undo2 className="mr-2 h-4 w-4" />
                  Desfazer
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Resubmit Dialog */}
      <AlertDialog open={resubmitDialogOpen} onOpenChange={setResubmitDialogOpen}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Reenviar com novos arquivos</AlertDialogTitle>
            <AlertDialogDescription>
              Isso vai desfazer a entrega atual e reenviar a tarefa com os arquivos selecionados.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="py-4 space-y-4">
            {/* File Upload Area */}
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-6 text-center hover:border-muted-foreground/50 transition-colors">
              <input
                type="file"
                id="resubmit-files"
                multiple
                className="hidden"
                onChange={handleFileSelect}
              />
              <label
                htmlFor="resubmit-files"
                className="cursor-pointer flex flex-col items-center gap-2"
              >
                <Upload className="h-8 w-8 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  Clique para selecionar arquivos
                </span>
                <span className="text-xs text-muted-foreground/70">
                  ou arraste e solte aqui
                </span>
              </label>
            </div>

            {/* Selected Files List */}
            {resubmitFiles.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Arquivos selecionados:</p>
                <ul className="space-y-1">
                  {resubmitFiles.map((file, idx) => (
                    <li
                      key={idx}
                      className="flex items-center justify-between gap-2 p-2 bg-muted/50 rounded text-sm"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <Files className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="truncate">{file.name}</span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          ({(file.size / 1024).toFixed(1)} KB)
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => handleRemoveFile(idx)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={resubmitMutation.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleResubmitConfirm}
              disabled={resubmitMutation.isPending || resubmitFiles.length === 0}
            >
              {resubmitMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processando...
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Reenviar ({resubmitFiles.length} arquivo{resubmitFiles.length !== 1 ? "s" : ""})
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
