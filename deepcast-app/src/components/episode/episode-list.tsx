"use client"

import { EpisodeCard } from "./episode-card"
import type { Database } from "@/types/database"

type Episode = Database["public"]["Tables"]["episodes"]["Row"]

interface EpisodeListProps {
  episodes: Episode[]
}

export function EpisodeList({ episodes }: EpisodeListProps) {
  if (episodes.length === 0) {
    return (
      <p className="py-12 text-center text-muted-foreground">
        エピソードがありません
      </p>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {episodes.map((episode) => (
        <EpisodeCard key={episode.id} episode={episode} />
      ))}
    </div>
  )
}
