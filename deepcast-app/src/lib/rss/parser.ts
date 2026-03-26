import Parser from "rss-parser"

const parser = new Parser({
  customFields: {
    item: [
      ["itunes:duration", "itunesDuration"],
      ["itunes:image", "itunesImage"],
    ],
  },
})

export interface ParsedEpisode {
  guid: string
  title: string
  description: string
  audioUrl: string
  duration: number | null
  publishedAt: string | null
  imageUrl: string | null
}

export interface ParsedFeed {
  title: string
  description: string
  feedUrl: string
  artworkUrl: string | null
  author: string | null
  websiteUrl: string | null
  episodes: ParsedEpisode[]
}

function parseDuration(raw: string | undefined): number | null {
  if (!raw) return null
  if (/^\d+$/.test(raw)) return parseInt(raw, 10)
  const parts = raw.split(":").map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return null
}

export async function parseFeed(feedUrl: string): Promise<ParsedFeed> {
  const feed = await parser.parseURL(feedUrl)

  const episodes: ParsedEpisode[] = (feed.items || []).map((item) => ({
    guid: item.guid || item.link || item.title || "",
    title: item.title || "Untitled",
    description: item.contentSnippet || item.content || "",
    audioUrl: item.enclosure?.url || "",
    duration: parseDuration(
      (item as unknown as Record<string, string>).itunesDuration
    ),
    publishedAt: item.isoDate || null,
    imageUrl:
      (item as unknown as Record<string, { $?: { href?: string } }>).itunesImage?.$
        ?.href || null,
  }))

  return {
    title: feed.title || "Untitled Podcast",
    description: feed.description || "",
    feedUrl,
    artworkUrl: feed.image?.url || null,
    author: feed.creator || null,
    websiteUrl: feed.link || null,
    episodes,
  }
}
