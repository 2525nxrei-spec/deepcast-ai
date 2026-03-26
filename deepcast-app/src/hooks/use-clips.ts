"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { createClient } from "@/lib/supabase/client"
import type { Database } from "@/types/database"

type Clip = Database["public"]["Tables"]["clips"]["Row"]

export function useClips(episodeId?: string) {
  return useQuery<Clip[]>({
    queryKey: ["clips", episodeId],
    queryFn: async () => {
      const supabase = createClient()
      let query = supabase
        .from("clips")
        .select("*")
        .order("created_at", { ascending: false })

      if (episodeId) {
        query = query.eq("episode_id", episodeId)
      }

      const { data, error } = await query
      if (error) throw error
      return (data ?? []) as unknown as Clip[]
    },
  })
}

export function useCreateClip() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (clip: {
      episode_id: string
      start_sec: number
      end_sec: number
      transcript?: string
      memo?: string
    }) => {
      const supabase = createClient()
      const {
        data: { user },
      } = await supabase.auth.getUser()
      if (!user) throw new Error("Not authenticated")

      const { data, error } = await supabase
        .from("clips")
        .insert({ ...clip, user_id: user.id })
        .select()
        .single()

      if (error) throw error
      return data as unknown as Clip
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["clips", data.episode_id] })
      queryClient.invalidateQueries({ queryKey: ["clips"] })
    },
  })
}

export function useExportClips() {
  return {
    toMarkdown: (
      clips: {
        start_sec: number
        end_sec: number
        transcript: string | null
        memo: string | null
        title?: string
      }[]
    ) => {
      const lines = clips.map((clip) => {
        const time = `${formatSec(clip.start_sec)} - ${formatSec(clip.end_sec)}`
        const title = clip.title || "Unknown"
        return `## ${title}\n**${time}**\n\n${clip.transcript || ""}\n\n> ${clip.memo || ""}\n`
      })
      return lines.join("\n---\n\n")
    },
  }
}

function formatSec(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, "0")}`
}
