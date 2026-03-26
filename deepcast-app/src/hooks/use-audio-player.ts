"use client"

import { useAudio } from "@/providers/audio-provider"
import { useCallback, useMemo } from "react"

const PLAYBACK_RATES = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]

export function useAudioPlayer() {
  const audio = useAudio()

  const progress = useMemo(() => {
    if (!audio.duration) return 0
    return (audio.currentTime / audio.duration) * 100
  }, [audio.currentTime, audio.duration])

  const timeLeft = useMemo(() => {
    return Math.max(0, audio.duration - audio.currentTime)
  }, [audio.duration, audio.currentTime])

  const togglePlay = useCallback(() => {
    if (audio.isPlaying) {
      audio.pause()
    } else {
      audio.resume()
    }
  }, [audio])

  const skipForward = useCallback(
    (seconds = 30) => {
      audio.seek(Math.min(audio.currentTime + seconds, audio.duration))
    },
    [audio]
  )

  const skipBackward = useCallback(
    (seconds = 15) => {
      audio.seek(Math.max(audio.currentTime - seconds, 0))
    },
    [audio]
  )

  const cyclePlaybackRate = useCallback(() => {
    const currentIndex = PLAYBACK_RATES.indexOf(audio.playbackRate)
    const nextIndex = (currentIndex + 1) % PLAYBACK_RATES.length
    audio.setRate(PLAYBACK_RATES[nextIndex])
  }, [audio])

  const formatTime = useCallback((seconds: number) => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
    return `${m}:${s.toString().padStart(2, "0")}`
  }, [])

  return {
    ...audio,
    progress,
    timeLeft,
    togglePlay,
    skipForward,
    skipBackward,
    cyclePlaybackRate,
    formatTime,
    playbackRates: PLAYBACK_RATES,
  }
}
