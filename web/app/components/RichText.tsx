"use client";

/**
 * Minimal chat-message renderer — ported from the prototype's
 * RichText.tsx: supports `**bold**` and newlines, splitting on plain
 * string markers (no `dangerouslySetInnerHTML`, so nothing in a model's
 * output can inject HTML). Also lightly highlights `[ISSUE_KEY]`-style
 * bracket references the Chat Orchestrator's system prompt encourages
 * (worker/app/chat/orchestrator.py) — presentational only, not a link:
 * an issue_key can belong to more than one agent's finding, so this MVP
 * doesn't try to resolve it to a specific clickable Finding.
 */
const BRACKET_RE = /(\[[A-Z0-9_]+\]|【[^】]+】)/g;

function renderInlineSegment(segment: string, key: string) {
  const parts = segment.split(BRACKET_RE);
  return (
    <span key={key}>
      {parts.map((part, i) =>
        BRACKET_RE.test(part) ? (
          <span
            key={i}
            className="rounded px-1 py-0.5 text-xs font-medium"
            style={{ background: "var(--brand-bg)", color: "var(--brand)" }}
          >
            {part.replace(/[[\]【】]/g, "")}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  );
}

export function RichText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, lineIdx) => {
        const boldParts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <span key={lineIdx}>
            {boldParts.map((part, i) =>
              part.startsWith("**") && part.endsWith("**") ? (
                <strong key={i}>{renderInlineSegment(part.slice(2, -2), `b-${i}`)}</strong>
              ) : (
                renderInlineSegment(part, `p-${i}`)
              )
            )}
            {lineIdx < lines.length - 1 && <br />}
          </span>
        );
      })}
    </>
  );
}
