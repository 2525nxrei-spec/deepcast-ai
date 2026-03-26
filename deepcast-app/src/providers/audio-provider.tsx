"use client"

import {
  createContext,
  useContext,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from "react"

interface AudioState {
  episodeId: string | null
  title: string
  audioUrl: string
  currentTime: number
  duration: number
  playbackRate: number
  isPlaying: boolean
}

interface AudioContextType extends AudioState {
  play: (episodeId: string, title: string, audioUrl: string) => void
  pause: () => void
  resume: () => void
  seek: (time: number) => void
  setRate: (rate: number) => void
  audioRef: React.RefObject<HTMLAudioElement | null>
}

const AudioContext = createContext<AudioContextType | null>(null)

export function AudioProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [state, setState] = useState<AudioState>({
    episodeId: null,
    title: "",
    audioUrl: "",
    currentTime: 0,
    duration: 0,
    playbackRate: 1.0,
    isPlaying: false,
  })

  const play = useCallback(
    (episodeId: string, title: string, audioUrl: string) => {
      const audio = audioRef.current
      if (!audio) return

      audio.src = audioUrl
      audio.playbackRate = state.playbackRate
      audio.play()

      setState((prev) => ({
        ...prev,
        episodeId,
        title,
        audioUrl,
        isPlaying: true,
        currentTime: 0,
      }))

      if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
          title,
          artist: "DeepCast AI",
        })
      }
    },
    [state.playbackRate]
  )

  const pause = useCallback(() => {
    audioRef.current?.pause()
    setState((prev) => ({ ...prev, isPlaying: false }))
  }, [])

  const resume = useCallback(() => {
    audioRef.current?.play()
    setState((prev) => ({ ...prev, isPlaying: true }))
  }, [])

  const seek = useCallback((time: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = time
    setState((prev) => ({ ...prev, currentTime: time }))
  }, [])

  const setRate = useCallback((rate: number) => {
    const audio = audioRef.current
    if (audio) audio.playbackRate = rate
    setState((prev) => ({ ...prev, playbackRate: rate }))
  }, [])

  return (
    <AudioContext.Provider
      value={{ ...state, play, pause, resume, seek, setRate, audioRef }}
    >
      {children}
      <audio
        ref={audioRef}
        onTimeUpdate={() => {
          const audio = audioRef.current
          if (audio) {
            setState((prev) => ({ ...prev, currentTime: audio.currentTime }))
          }
        }}
        onLoadedMetadata={() => {
          const audio = audioRef.current
          if (audio) {
            setState((prev) => ({ ...prev, duration: audio.duration }))
          }
        }}
        onEnded={() => {
          setState((prev) => ({ ...prev, isPlaying: false }))
        }}
      />
    </AudioContext.Provider>
  )
}

export function useAudio() {
  const context = useContext(AudioContext)
  if (!context) throw new Error("useAudio must be used within AudioProvider")
  return context
}
