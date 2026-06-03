"use client"

import { X } from "lucide-react"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"

interface UploadProgressProps {
  fileName: string
  progress: number
  uploadedBytes: number
  totalBytes: number
  onCancel: () => void
}

export function UploadProgress({
  fileName,
  progress,
  uploadedBytes,
  totalBytes,
  onCancel,
}: UploadProgressProps) {
  const [displayProgress, setDisplayProgress] = useState(0)

  useEffect(() => {
    setDisplayProgress(progress)
  }, [progress])

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B"
    const k = 1024
    const sizes = ["B", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border bg-muted/50 p-3">
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-medium">{fileName}</p>
        <div className="mt-2 flex items-center gap-2">
          <Progress value={displayProgress} className="h-2" />
          <span className="text-xs text-muted-foreground w-12 text-right">
            {Math.round(displayProgress)}%
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {formatBytes(uploadedBytes)} / {formatBytes(totalBytes)}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={onCancel}
        aria-label="取消上传"
      >
        <X className="size-4" />
      </Button>
    </div>
  )
}
