"use client"

import type { Chapter } from "@/types/database"
import { cn } from "@/lib/utils"

interface ChapterListProps {
  chapters: Chapter[]
  onChapterClick: (startSec: number) => void
  currentTime: number
}

function formatSec(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h > 0)
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
  return `${m}:${s.toString().padStart(2, "0")}`
}

function isCurrentChapter(chapter: Chapter, currentTime: number): boolean {
  return currentTime >= chapter.start_sec && currentTime < chapter.end_sec
}

export function ChapterList({
  chapters,
  onChapterClick,
  currentTime,
}: ChapterListProps) {
  if (chapters.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        チャプター情報がありません
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-muted-foreground">
        チャプター
      </h3>
      <ul className="space-y-1.5">
        {chapters.map((chapter, index) => {
          const active = isCurrentChapter(chapter, currentTime)
          return (
            <li key={index}>
              <button
                type="button"
                onClick={() => onChapterClick(chapter.start_sec)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition-colors",
                  active
                    ? "border-[#3a8a44]/40 bg-[#3a8a44]/10"
                    : "border-border bg-card hover:bg-muted"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p
                      className={cn(
                        "text-sm font-medium leading-snug",
                        active && "text-[#3a8a44]"
                      )}
                    >
                      {active && (
                        <span className="mr-1.5 inline-block size-2 rounded-full bg-[#3a8a44] animate-pulse" />
                      )}
                      {chapter.title}
                    </p>
                    {chapter.summary && (
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {chapter.summary}
                      </p>
                    )}
                  </div>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {formatSec(chapter.start_sec)}
                  </span>
                </div>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
