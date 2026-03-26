"use client"

import { useState } from "react"
import { Scissors, Check } from "lucide-react"
import { useCreateClip } from "@/hooks/use-clips"

interface ClipButtonProps {
  episodeId: string
  currentTime: number
}

export function ClipButton({ episodeId, currentTime }: ClipButtonProps) {
  const createClip = useCreateClip()
  const [showToast, setShowToast] = useState(false)

  const handleClip = () => {
    if (createClip.isPending) return

    const startSec = Math.floor(currentTime)
    const endSec = startSec + 30

    createClip.mutate(
      {
        episode_id: episodeId,
        start_sec: startSec,
        end_sec: endSec,
      },
      {
        onSuccess: () => {
          setShowToast(true)
          setTimeout(() => setShowToast(false), 2000)
        },
      }
    )
  }

  return (
    <>
      <button
        onClick={handleClip}
        disabled={createClip.isPending}
        aria-label="クリップを保存"
        className="fixed bottom-24 right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-[#3a8a44] text-white shadow-lg transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 sm:bottom-28 sm:right-6"
      >
        {createClip.isPending ? (
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
        ) : (
          <Scissors className="h-5 w-5" />
        )}
      </button>

      {/* トースト通知 */}
      {showToast && (
        <div className="fixed bottom-40 right-4 z-50 flex items-center gap-2 rounded-lg bg-[#3a8a44] px-4 py-2.5 text-sm font-medium text-white shadow-lg animate-in fade-in slide-in-from-bottom-2 sm:right-6">
          <Check className="h-4 w-4" />
          クリップを保存しました
        </div>
      )}
    </>
  )
}
