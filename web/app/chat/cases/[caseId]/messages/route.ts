/**
 * Dedicated streaming proxy for POSTing a chat message — deliberately
 * OUTSIDE /api/* for the exact same reason as
 * web/app/sse/cases/[caseId]/stream/route.ts: Next's generic rewrite
 * proxy does not forward a long-lived response chunk-by-chunk in this
 * project's Next.js version (verified live for the SSE case; a streamed
 * `text/plain` POST response is the same underlying mechanism, so this
 * route is served from its own path rather than risking the same silent
 * buffering).
 *
 * GET (fetching message history) has no such problem — it's a normal
 * request/response, so it still goes through web/app/lib/api.ts's usual
 * /api/* path.
 */
export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await context.params;
  const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";
  const body = await request.text();

  const upstream = await fetch(`${apiUrl}/cases/${caseId}/chat/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal: request.signal,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}
