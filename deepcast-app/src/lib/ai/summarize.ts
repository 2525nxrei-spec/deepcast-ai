import OpenAI from "openai"
import type { Chapter } from "@/types/database"

interface SummarizeResult {
  summary: string
  chapters: Chapter[]
  keyPoints: string[]
}

export async function summarizeTranscript(
  transcript: string,
  segments: { start: number; end: number; text: string }[]
): Promise<SummarizeResult> {
  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
  const segmentText = segments
    .map((s) => `[${formatTime(s.start)}] ${s.text}`)
    .join("\n")

  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      {
        role: "system",
        content: `あなたはポッドキャストの内容を分析するAIです。
以下のタイムスタンプ付き文字起こしを分析し、JSON形式で返してください。

出力形式:
{
  "summary": "マークダウン形式の要約（300-500字）",
  "chapters": [
    {
      "title": "チャプタータイトル",
      "start_sec": 開始秒数,
      "end_sec": 終了秒数,
      "summary": "チャプターの要約（1-2文）"
    }
  ],
  "key_points": ["要点1", "要点2", "要点3"]
}

チャプターは3-7個に分割してください。`,
      },
      {
        role: "user",
        content: segmentText || transcript,
      },
    ],
    response_format: { type: "json_object" },
    temperature: 0.3,
  })

  const content = response.choices[0]?.message?.content
  if (!content) throw new Error("No response from GPT-4o")

  const result = JSON.parse(content) as SummarizeResult

  return {
    summary: result.summary,
    chapters: result.chapters.map((ch) => ({
      title: ch.title,
      start_sec: ch.start_sec,
      end_sec: ch.end_sec,
      summary: ch.summary,
    })),
    keyPoints: result.keyPoints || (result as unknown as { key_points?: string[] }).key_points || [],
  }
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, "0")}`
}
