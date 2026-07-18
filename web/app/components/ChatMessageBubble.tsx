"use client";

/**
 * Chat bubble — ported from the prototype's ChatMessageBubble.tsx layout
 * (right-aligned brand bubble for the Credit Officer, left-aligned
 * surface-raised bubble with an avatar for the agent), wired to real
 * `ChatMessageDto` rows instead of the prototype's mock `ChatMessage`.
 */
import { Sparkles, User2 } from "lucide-react";
import { RichText } from "./RichText";
import { formatDateTime } from "./ui";
import { useI18n } from "../lib/i18n";

export function ChatMessageBubble({
  role,
  content,
  timestamp,
  streaming = false,
}: {
  role: "USER" | "ASSISTANT";
  content: string;
  timestamp?: string;
  streaming?: boolean;
}) {
  const { lang } = useI18n();
  const isOfficer = role === "USER";

  return (
    <div className={`flex items-start gap-2 ${isOfficer ? "flex-row-reverse" : ""}`}>
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
        style={
          isOfficer
            ? { background: "var(--brand)", color: "#fff" }
            : { background: "var(--brand-bg)", color: "var(--brand)" }
        }
      >
        {isOfficer ? <User2 size={14} /> : <Sparkles size={14} />}
      </span>
      <div
        className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${isOfficer ? "rounded-tr-sm" : "rounded-tl-sm border"}`}
        style={
          isOfficer
            ? { background: "var(--brand)", color: "#fff" }
            : { background: "var(--surface-raised)", borderColor: "var(--border-hairline)", color: "var(--text-primary)" }
        }
      >
        <RichText text={content} />
        {streaming && <span className="ml-0.5 animate-pulse">▍</span>}
        {timestamp && (
          <div
            className="mt-1 text-right text-[11px]"
            style={{ color: isOfficer ? "rgba(255,255,255,0.7)" : "var(--text-muted-2)" }}
          >
            {formatDateTime(timestamp, lang)}
          </div>
        )}
      </div>
    </div>
  );
}
