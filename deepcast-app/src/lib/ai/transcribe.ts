import OpenAI from "openai"

export interface TranscriptionResult {
  fullText: string
  segments: { start: number; end: number; text: string }[]
}

export async function transcribeAudio(
  audioUrl: string
): Promise<TranscriptionResult> {
  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
  const response = await fetch(audioUrl)
  const audioBuffer = await response.arrayBuffer()
  const file = new File([audioBuffer], "audio.mp3", { type: "audio/mpeg" })

  const transcription = await openai.audio.transcriptions.create({
    file,
    model: "whisper-1",
    response_format: "verbose_json",
    timestamp_granularities: ["segment"],
    language: "ja",
  })

  const segments = (
    transcription as unknown as {
      segments?: { start: number; end: number; text: string }[]
    }
  ).segments || []

  return {
    fullText: transcription.text,
    segments: segments.map((s) => ({
      start: s.start,
      end: s.end,
      text: s.text.trim(),
    })),
  }
}
