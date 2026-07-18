"use client";

/**
 * Chat/memo content renderer — replaces the old hand-rolled version that
 * only understood `**bold**` and newlines. Both the Chat Orchestrator's
 * replies (worker/app/chat/orchestrator.py) and Credit Memo sections
 * (api/app/routers/memo.py, sourced from finding claims) are full LLM-
 * generated markdown — headings, bullet/numbered lists, and occasionally
 * whole tables (e.g. Collateral & Legal Agent's checklist finding renders
 * a `| checklist_id | required_document | ... |` table) — which the old
 * renderer showed as literal `**`/`|` characters. `react-markdown` +
 * `remark-gfm` (tables/strikethrough/task lists) handles all of that
 * properly, still with no `dangerouslySetInnerHTML` — react-markdown
 * builds a React element tree, nothing in a model's output can inject
 * raw HTML.
 *
 * `[ISSUE_KEY]` / `【...】` bracket highlighting (this app's own
 * convention, not markdown — worker/app/chat/orchestrator.py's system
 * prompt encourages citing issue_keys this way) is preserved by
 * overriding the block-level components (`p`/`li`/`td`/`th`) and running
 * the same split-and-wrap logic over their text children.
 */
import { Children, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Two regexes on purpose: BRACKET_SPLIT_RE (global) drives `.split()`;
// BRACKET_MATCH_RE (anchored, no `g`) checks each resulting piece. The
// old version reused one global-flagged regex for both `.split()` and
// `.test()` — a global regex's `.test()` advances its own `lastIndex`,
// so alternating pieces could silently mismatch depending on call order.
const BRACKET_SPLIT_RE = /(\[[A-Z0-9_]+\]|【[^】]+】)/g;
const BRACKET_MATCH_RE = /^(\[[A-Z0-9_]+\]|【[^】]+】)$/;

function highlightBrackets(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    const parts = child.split(BRACKET_SPLIT_RE);
    if (parts.length === 1) return child;
    return parts.map((part, i) =>
      BRACKET_MATCH_RE.test(part) ? (
        <span
          key={i}
          className="rounded px-1 py-0.5 text-xs font-medium"
          style={{ background: "var(--brand-bg)", color: "var(--brand)" }}
        >
          {part.replace(/[[\]【】]/g, "")}
        </span>
      ) : (
        part
      )
    );
  });
}

function BracketAwareP({ children }: { children?: ReactNode }) {
  return <p>{highlightBrackets(children)}</p>;
}

function BracketAwareLi({ children }: { children?: ReactNode }) {
  return <li>{highlightBrackets(children)}</li>;
}

const hairline = "var(--border-hairline)";

export function RichText({ text }: { text: string }) {
  return (
    <div className="rich-text space-y-1.5 text-sm leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: BracketAwareP,
          li: BracketAwareLi,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" style={{ color: "var(--brand)", textDecoration: "underline" }}>
              {children}
            </a>
          ),
          code: ({ children }) => (
            <code
              className="rounded px-1 py-0.5 font-mono text-xs"
              style={{ background: "var(--surface-1)" }}
            >
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre
              className="overflow-x-auto rounded-lg p-2 font-mono text-xs"
              style={{ background: "var(--surface-1)" }}
            >
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="border-collapse text-xs" style={{ borderColor: hairline }}>
                {children}
              </table>
            </div>
          ),
          th: (props) => (
            <th
              className="border px-2 py-1 text-left font-semibold"
              style={{ borderColor: hairline, background: "var(--surface-1)" }}
            >
              {highlightBrackets(props.children)}
            </th>
          ),
          td: (props) => (
            <td className="border px-2 py-1" style={{ borderColor: hairline }}>
              {highlightBrackets(props.children)}
            </td>
          ),
          ul: ({ children }) => <ul className="list-outside list-disc space-y-0.5 pl-4">{children}</ul>,
          ol: ({ children }) => <ol className="list-outside list-decimal space-y-0.5 pl-4">{children}</ol>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
