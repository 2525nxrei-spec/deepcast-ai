/**
 * レスポンス生成ユーティリティ
 */

export function errorResponse(message, code = 400) {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status: code,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

export function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify({ ok: true, ...data }), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
