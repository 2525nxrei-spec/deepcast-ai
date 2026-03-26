"use client"

import { useQuery } from "@tanstack/react-query"
import { createClient } from "@/lib/supabase/client"
import type { Database } from "@/types/database"

type Episode = Database["public"]["Tables"]["episodes"]["Row"]

interface EpisodeWithRelations extends Episode {
  summaries: {
    summary: string
    chapters: unknown[]
    key_points: unknown[]
  } | null
  transcripts: {
    full_text: string
    segments: unknown[]
  } | null
}

export function useEpisodes(podcastId?: string) {
  return useQuery<Episode[]>({
    queryKey: ["episodes", podcastId],
    queryFn: async () => {
      const supabase = createClient()
      let query = supabase
        .from("episodes")
        .select("*")
        .order("published_at", { ascending: false })
        .limit(50)

      if (podcastId) {
        query = query.eq("podcast_id", podcastId)
      }

      const { data, error } = await query
      if (error) throw error
      return (data ?? []) as unknown as Episode[]
    },
  })
}

export function useEpisode(id: string) {
  return useQuery<EpisodeWithRelations>({
    queryKey: ["episode", id],
    queryFn: async () => {
      const supabase = createClient()
      const { data, error } = await supabase
        .from("episodes")
        .select("*, transcripts(*), summaries(*)")
        .eq("id", id)
        .single()

      if (error) throw error
      return data as unknown as EpisodeWithRelations
    },
    enabled: !!id,
  })
}
