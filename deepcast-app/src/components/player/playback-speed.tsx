"use client"

import { useState, useRef, useEffect } from "react"
import { cn } from "@/lib/utils"

const RATE_OPTIONS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]

interface PlaybackSpeedProps {
  currentRate: number
  onRateChange: (rate: number) => void
}

export function PlaybackSpeed({
  currentRate,
  onRateChange,
}: PlaybackSpeedProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // 外側クリックで閉じる
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [open])

  // Escで閉じる
  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [open])

  const label = currentRate === 1.0 ? "1x" : `${currentRate}x`

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="再生速度"
        aria-expanded={open}
        className={cn(
          "flex h-8 min-w-[3rem] items-center justify-center rounded-md px-2 text-xs font-semibold tabular-nums transition-colors",
          "bg-muted text-foreground hover:bg-muted/80",
          open && "ring-2 ring-[#3a8a44]/40"
        )}
      >
        {label}
      </button>

      {open && (
        <div className="absolute bottom-full right-0 mb-2 w-28 rounded-lg border border-border bg-popover p-1 shadow-lg">
          <p className="px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            再生速度
          </p>
          {RATE_OPTIONS.map((rate) => (
            <button
              key={rate}
              type="button"
              onClick={() => {
                onRateChange(rate)
                setOpen(false)
              }}
              className={cn(
                "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm tabular-nums transition-colors",
                rate === currentRate
                  ? "bg-[#3a8a44]/10 font-semibold text-[#3a8a44]"
                  : "text-foreground hover:bg-muted"
              )}
            >
              <span>{rate}x</span>
              {rate === currentRate && (
                <span className="size-1.5 rounded-full bg-[#3a8a44]" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
