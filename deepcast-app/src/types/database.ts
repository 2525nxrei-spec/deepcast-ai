export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string
          display_name: string | null
          avatar_url: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id: string
          display_name?: string | null
          avatar_url?: string | null
        }
        Update: {
          display_name?: string | null
          avatar_url?: string | null
        }
        Relationships: []
      }
      podcasts: {
        Row: {
          id: string
          title: string
          description: string | null
          feed_url: string
          artwork_url: string | null
          author: string | null
          website_url: string | null
          last_synced: string | null
          created_at: string
        }
        Insert: {
          id?: string
          title: string
          feed_url: string
          description?: string | null
          artwork_url?: string | null
          author?: string | null
          website_url?: string | null
          last_synced?: string | null
        }
        Update: {
          title?: string
          description?: string | null
          feed_url?: string
          artwork_url?: string | null
          author?: string | null
          website_url?: string | null
          last_synced?: string | null
        }
        Relationships: []
      }
      subscriptions: {
        Row: {
          id: string
          user_id: string
          podcast_id: string
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          podcast_id: string
        }
        Update: {
          user_id?: string
          podcast_id?: string
        }
        Relationships: []
      }
      episodes: {
        Row: {
          id: string
          podcast_id: string
          guid: string
          title: string
          description: string | null
          audio_url: string
          duration: number | null
          published_at: string | null
          image_url: string | null
          created_at: string
        }
        Insert: {
          id?: string
          podcast_id: string
          guid: string
          title: string
          audio_url: string
          description?: string | null
          duration?: number | null
          published_at?: string | null
          image_url?: string | null
        }
        Update: {
          title?: string
          description?: string | null
          audio_url?: string
          duration?: number | null
          published_at?: string | null
          image_url?: string | null
        }
        Relationships: []
      }
      transcripts: {
        Row: {
          id: string
          episode_id: string
          full_text: string
          segments: Json
          language: string
          model: string
          created_at: string
        }
        Insert: {
          id?: string
          episode_id: string
          full_text: string
          segments?: Json
          language?: string
          model?: string
        }
        Update: {
          full_text?: string
          segments?: Json
        }
        Relationships: []
      }
      summaries: {
        Row: {
          id: string
          episode_id: string
          summary: string
          chapters: Json
          key_points: Json
          model: string
          created_at: string
        }
        Insert: {
          id?: string
          episode_id: string
          summary: string
          chapters?: Json
          key_points?: Json
          model?: string
        }
        Update: {
          summary?: string
          chapters?: Json
          key_points?: Json
        }
        Relationships: []
      }
      playback_states: {
        Row: {
          id: string
          user_id: string
          episode_id: string
          position: number
          playback_rate: number
          completed: boolean
          updated_at: string
        }
        Insert: {
          id?: string
          user_id: string
          episode_id: string
          position?: number
          playback_rate?: number
          completed?: boolean
        }
        Update: {
          position?: number
          playback_rate?: number
          completed?: boolean
        }
        Relationships: []
      }
      clips: {
        Row: {
          id: string
          user_id: string
          episode_id: string
          start_sec: number
          end_sec: number
          transcript: string | null
          memo: string | null
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          episode_id: string
          start_sec: number
          end_sec: number
          transcript?: string | null
          memo?: string | null
        }
        Update: {
          start_sec?: number
          end_sec?: number
          transcript?: string | null
          memo?: string | null
        }
        Relationships: []
      }
    }
    Views: Record<string, never>
    Functions: Record<string, never>
    Enums: Record<string, never>
    CompositeTypes: Record<string, never>
  }
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
}

export interface Chapter {
  title: string
  start_sec: number
  end_sec: number
  summary: string
}
