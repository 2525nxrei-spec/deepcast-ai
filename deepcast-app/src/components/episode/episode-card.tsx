"use client"

import Link from "next/link"
import { Play, Pause } from "lucide-react"
import { useAudio } from "@/providers/audio-provider"
import type { Database } from "@/types/database"

type Episode = Database["public"]["Tables"]["episodes"]["Row"]

interface EpisodeCardProps {
  episode: Episode
}

export function EpisodeCard({ episode }: EpisodeCardProps) {
  const { play, pause, isPlaying, episodeId } = useAudio()

  const isCurrentlyPlaying = isPlaying && episodeId === episode.id

  const handlePlayClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    if (isCurrentlyPlaying) {
      pause()
    } else {
      play(episode.id, episode.title, episode.audio_url)
    }
  }

  const formattedDate = episode.published_at
    ? new Date(episode.published_at).toLocaleDateString("ja-JP")
    : null

  const formattedDuration = episode.duration
    ? `${Math.floor(episode.duration / 60)}分`
    : null

  return (
    <Link
      href={`/episodes/${episode.id}`}
      className="group block overflow-hidden rounded-xl border border-border bg-card transition-shadow hover:shadow-md"
    >
      <div className="flex gap-3 p-3 sm:p-4">
        {/* サムネイル */}
        <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-muted sm:h-24 sm:w-24">
          {episode.image_url ? (
            <img
              src={episode.image_url}
              alt={episode.title}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-[#3a8a44]/10">
              <svg
                className="h-8 w-8 text-[#3a8a44]/40"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path d="M9 18V5l12-2v13" />
                <circle cx="6" cy="18" r="3" />
                <circle cx="18" cy="16" r="3" />
              </svg>
            </div>
          )}

          {/* 再生ボタンオーバーレイ */}
          <button
            onClick={handlePlayClick}
            aria-label={isCurrentlyPlaying ? "一時停止" : "再生"}
            className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/30"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#3a8a44] text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
              {isCurrentlyPlaying ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4 translate-x-px" />
              )}
            </span>
          </button>
        </div>

        {/* テキスト情報 */}
        <div className="flex min-w-0 flex-1 flex-col justify-between">
          <div>
            <h3 className="line-clamp-1 text-sm font-bold leading-snug sm:text-base">
              {episode.title}
            </h3>
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground sm:text-sm">
              {episode.description}
            </p>
          </div>

          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
            {formattedDate && <span>{formattedDate}</span>}
            {formattedDuration && <span>{formattedDuration}</span>}
          </div>
        </div>
      </div>
    </Link>
  )
}
