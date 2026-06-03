"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react"
import { ChevronRight, Play, Upload } from "lucide-react"

import {
  TaskSummary,
  LocalDirection,
  completeChunkUpload,
  createTask,
  getChunkUploadStatus,
  getUploadSettings,
  initChunkUpload,
  listTasks,
  uploadChunk,
  uploadLocalTask,
} from "@/lib/api"
import { useI18n } from "@/lib/i18n"
import { statusBadgeClass } from "@/lib/status"
import { AppHeader } from "@/components/app-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { UploadProgress } from "@/components/upload-progress"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

function isActive(status: string) {
  return status === "queued" || status === "running"
}

function formatTime(value: string | null) {
  if (!value) return ""
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function shortUrl(url: string) {
  return url.replace(/^https?:\/\/(www\.)?/, "")
}

function activeCount(tasks: TaskSummary[]) {
  return tasks.filter((t) => isActive(t.status)).length
}

export default function Home() {
  const router = useRouter()
  const { activeTasksText, stageLabel, statusLabel, t } = useI18n()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [youtubeUrl, setYoutubeUrl] = useState("")
  const [bilibiliUrl, setBilibiliUrl] = useState("")
  const [localFile, setLocalFile] = useState<File | null>(null)
  const [localDirection, setLocalDirection] = useState<LocalDirection>("en-zh")
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<{
    fileName: string
    progress: number
    uploadedBytes: number
    totalBytes: number
  } | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  async function refreshTasks() {
    const { tasks: list } = await listTasks()
    setTasks(list)
  }

  useEffect(() => {
    let cancelled = false

    const loadTasks = async () => {
      try {
        const { tasks: list } = await listTasks()
        if (!cancelled) setTasks(list)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : t.home.loadError)
      }
    }

    loadTasks()
    const interval = window.setInterval(loadTasks, 2000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [t.home.loadError])

  function selectLocalFile(event: ChangeEvent<HTMLInputElement>) {
    setError("")
    setLocalFile(event.target.files?.[0] || null)
  }

  async function uploadWithChunks(file: File, direction: LocalDirection) {
    const settings = await getUploadSettings()
    const chunkSize = parseInt(settings.chunk_size_mb) * 1024 * 1024
    const concurrency = parseInt(settings.concurrency)
    const totalChunks = Math.ceil(file.size / chunkSize)

    const initResponse = await initChunkUpload(
      direction,
      file.name,
      file.size,
      totalChunks
    )

    const uploadId = initResponse.upload_id
    const actualChunkSize = initResponse.chunk_size

    setUploadProgress({
      fileName: file.name,
      progress: 0,
      uploadedBytes: 0,
      totalBytes: file.size,
    })

    const uploadedChunks = new Set<number>()
    let uploadedBytes = 0

    const uploadSingleChunk = async (chunkIndex: number, retryCount = 0): Promise<void> => {
      if (uploadedChunks.has(chunkIndex)) return

      const start = chunkIndex * actualChunkSize
      const end = Math.min(start + actualChunkSize, file.size)
      const chunk = file.slice(start, end)

      try {
        const response = await uploadChunk(uploadId, chunkIndex, chunk)
        if (response.uploaded_chunks.includes(chunkIndex)) {
          uploadedChunks.add(chunkIndex)
          uploadedBytes += chunk.size

          setUploadProgress({
            fileName: file.name,
            progress: (uploadedChunks.size / totalChunks) * 100,
            uploadedBytes,
            totalBytes: file.size,
          })
        }
      } catch (error) {
        if (retryCount < 3) {
          await new Promise(resolve => setTimeout(resolve, 1000 * (retryCount + 1)))
          return uploadSingleChunk(chunkIndex, retryCount + 1)
        }
        throw error
      }
    }

    const uploadQueue: number[] = []
    for (let i = 0; i < totalChunks; i++) {
      uploadQueue.push(i)
    }

    const uploadNextBatch = async (): Promise<void> => {
      if (uploadQueue.length === 0) return

      const batch = uploadQueue.splice(0, concurrency)
      const results = await Promise.allSettled(batch.map(uploadSingleChunk))

      const failedIndices = results
        .map((result, index) => result.status === 'rejected' ? batch[index] : -1)
        .filter(index => index !== -1)

      if (failedIndices.length > 0) {
        uploadQueue.unshift(...failedIndices)
        await new Promise(resolve => setTimeout(resolve, 2000))
      }

      if (uploadQueue.length > 0) {
        await uploadNextBatch()
      }
    }

    await uploadNextBatch()

    // Verify all chunks are uploaded
    const status = await getChunkUploadStatus(uploadId)
    const missingChunks = []
    for (let i = 0; i < totalChunks; i++) {
      if (!status.uploaded_chunks.includes(i)) {
        missingChunks.push(i)
      }
    }

    // Upload missing chunks
    if (missingChunks.length > 0) {
      for (const chunkIndex of missingChunks) {
        await uploadSingleChunk(chunkIndex)
      }
    }

    const task = await completeChunkUpload(uploadId)

    setUploadProgress(null)
    return task
  }

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    const submittedUrl = youtubeUrl.trim() || bilibiliUrl.trim()
    if (!submittedUrl && !localFile) return
    setSubmitting(true)

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    try {
      let created
      if (localFile) {
        const settings = await getUploadSettings()
        if (settings.mode === "chunked") {
          created = await uploadWithChunks(localFile, localDirection)
        } else {
          created = await uploadLocalTask(localFile, localDirection)
        }
      } else {
        created = await createTask(submittedUrl)
      }

      setYoutubeUrl("")
      setBilibiliUrl("")
      setLocalFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
      refreshTasks().catch(() => undefined)
      router.push(`/tasks/${created.id}`)
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        setError("上传已取消")
      } else {
        setError(err instanceof Error ? err.message : t.home.createError)
      }
    } finally {
      setSubmitting(false)
      setUploadProgress(null)
      abortControllerRef.current = null
    }
  }

  function handleCancelUpload() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setUploadProgress(null)
    setSubmitting(false)
  }

  const queued = activeCount(tasks)
  const hasUrl = Boolean(youtubeUrl.trim() || bilibiliUrl.trim())
  const hasLocalFile = Boolean(localFile)
  const canSubmit = Boolean((hasUrl || hasLocalFile) && !submitting)

  return (
    <main className="min-h-screen bg-[linear-gradient(135deg,#fff5f5_0%,#f2fbff_48%,#fff4fa_100%)] text-foreground">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <AppHeader />

        <Card>
          <CardHeader>
            <CardTitle>{t.home.createTitle}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={submitTask} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="youtube-url">{t.home.youtubeLabel}</Label>
                <Input
                  id="youtube-url"
                  value={youtubeUrl}
                  onChange={(event) => setYoutubeUrl(event.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  disabled={Boolean(bilibiliUrl.trim()) || hasLocalFile}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="bilibili-url">{t.home.bilibiliLabel}</Label>
                <Input
                  id="bilibili-url"
                  value={bilibiliUrl}
                  onChange={(event) => setBilibiliUrl(event.target.value)}
                  placeholder="https://www.bilibili.com/video/BV..."
                  disabled={Boolean(youtubeUrl.trim()) || hasLocalFile}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
                <div className="space-y-2">
                  <Label htmlFor="local-video">{t.home.localVideoLabel}</Label>
                  <Input
                    ref={fileInputRef}
                    id="local-video"
                    type="file"
                    accept="video/*,.mp4,.mov,.m4v,.mkv,.webm,.avi,.flv,.wmv"
                    onChange={selectLocalFile}
                    disabled={hasUrl}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="local-direction">{t.home.localDirectionLabel}</Label>
                  <Select
                    value={localDirection}
                    onValueChange={(value) => setLocalDirection(value as LocalDirection)}
                    disabled={hasUrl}
                  >
                    <SelectTrigger id="local-direction" className="h-10">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en-zh">{t.home.localEnZh}</SelectItem>
                      <SelectItem value="zh-en">{t.home.localZhEn}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center justify-between gap-3">
                {queued > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    {activeTasksText(queued)}
                  </p>
                ) : (
                  <span />
                )}
                <Button type="submit" disabled={!canSubmit}>
                  {hasLocalFile ? <Upload className="size-4" /> : <Play className="size-4" />}
                  {submitting ? t.home.submitting : t.home.createTask}
                </Button>
              </div>
            </form>

            {error ? (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            ) : null}

            {uploadProgress ? (
              <UploadProgress
                fileName={uploadProgress.fileName}
                progress={uploadProgress.progress}
                uploadedBytes={uploadProgress.uploadedBytes}
                totalBytes={uploadProgress.totalBytes}
                onCancel={handleCancelUpload}
              />
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.home.taskHistory} ({tasks.length})</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            {tasks.length === 0 ? (
              <div className="px-6 py-12 text-center text-sm text-muted-foreground">
                {t.home.empty}
              </div>
            ) : (
              <ScrollArea className="max-h-[70dvh]">
                <ul className="flex flex-col">
                  {tasks.map((item) => (
                    <li key={item.id} className="border-b border-border/60 last:border-b-0">
                      <Link
                        href={`/tasks/${item.id}`}
                        className="flex w-full items-center gap-3 px-6 py-3 text-sm transition-colors hover:bg-muted/60"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-left font-medium text-zinc-900">
                            {item.title || shortUrl(item.url)}
                          </p>
                          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                            <Badge className={statusBadgeClass(item.status)}>{statusLabel(item.status)}</Badge>
                            <span>{formatTime(item.created_at)}</span>
                            {isActive(item.status) && item.current_stage ? (
                              <span>· {stageLabel(item.current_stage)}</span>
                            ) : null}
                          </div>
                        </div>
                        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                      </Link>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
