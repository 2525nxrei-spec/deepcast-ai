"use client"

import { useAudioPlayer } from "@/hooks/use-audio-player"
import { Button } from "@/components/ui/button"
import { PlaybackSpeed } from "@/components/player/playback-speed"
import { Play, Pause } from "lucide-react"

export function MiniPlayer() {
  const {
    episodeId,
    title,
    isPlaying,
    progress,
    currentTime,
    duration,
    playbackRate,
    togglePlay,
    seek,
    setRate,
    formatTime,
  } = useAudioPlayer()

  if (!episodeId) return null

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    seek(ratio * duration)
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background/95 backdrop-blur-sm supports-backdrop-filter:bg-background/80">
      {/* プログレスバー */}
      <div
        className="group h-1 w-full cursor-pointer bg-muted transition-all hover:h-2"
        onClick={handleProgressClick}
        role="progressbar"
        aria-label="再生位置"
        aria-valuenow={Math.round(progress)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-r-full transition-all"
          style={{
            width: `${progress}%`,
            backgroundColor: "#3a8a44",
          }}
        />
      </div>

      {/* コントロール */}
      <div className="flex h-16 items-center gap-3 px-4">
        {/* 再生/一時停止 */}
        <Button
          variant="ghost"
          size="icon"
          onClick={togglePlay}
          aria-label={isPlaying ? "一時停止" : "再生"}
          className="shrink-0"
        >
          {isPlaying ? (
            <Pause className="size-5 fill-current" />
          ) : (
            <Play className="size-5 fill-current" />
          )}
        </Button>

        {/* 曲名・時間 */}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium leading-tight">{title}</p>
          <p className="text-xs text-muted-foreground">
            {formatTime(currentTime)} / {formatTime(duration)}
          </p>
        </div>

        {/* 倍速 */}
        <PlaybackSpeed currentRate={playbackRate} onRateChange={setRate} />
      </div>
    </div>
  )
}
