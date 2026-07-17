/**
 * Dedicated streaming proxy for the SSE progress endpoint — deliberately
 * placed OUTSIDE /api/* (unlike every other web/app/lib/api.ts call).
 *
 * next.config.mjs's generic `/api/:path*` rewrite goes through Next's
 * built-in rewrite proxy, which does not forward a long-lived
 * `text/event-stream` response chunk-by-chunk in this project's Next.js
 * version — verified live: a browser EventSource against the rewritten
 * `/api/cases/{id}/stream` path opened successfully but received zero
 * "progress" messages over a full 30s window, while a direct Redis
 * SUBSCRIBE confirmed the backend really was publishing many messages
 * during that exact run. A literal Route Handler placed AT the same
 * `/api/cases/[caseId]/stream` path was ALSO silently ignored — the
 * response's own headers (`server: uvicorn`, no custom marker header)
 * showed the generic rewrite was still the one handling the request, not
 * the route handler — so any assumption that a literal file-based route
 * overrides a plain-array `rewrites()` entry did not hold here in
 * practice. Serving this from a path the rewrite pattern can never match
 * in the first place removes that ambiguity entirely.
 *
 * Passing `upstream.body` straight through (rather than buffering it
 * with `.text()`) preserves true chunk-by-chunk streaming, since Node's
 * built-in fetch (undici) gives a real WHATWG ReadableStream here.
 */
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await context.params;
  const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";

  const upstream = await fetch(`${apiUrl}/cases/${caseId}/stream`, {
    headers: { Accept: "text/event-stream" },
    signal: request.signal,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "Content-Encoding": "identity",
    },
  });
}
