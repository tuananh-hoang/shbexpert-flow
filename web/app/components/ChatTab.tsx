"use client";

/**
 * "Trao đổi & Kết luận" tab — ported from the prototype's ChatTab.tsx
 * layout (chat card 1fr + memo/action 340px column), wired to the REAL
 * Chat Orchestrator (ai-architecture_v2.md §11.8) instead of the
 * prototype's keyword-routed local chatEngine.ts: messages stream in
 * token-by-token via lib/api.ts::sendChatMessage.
 */
import { useEffect, useRef, useState } from "react";
import { Send, Sparkles } from "lucide-react";
import { fetchChatMessages, sendChatMessage } from "../lib/api";
import type { ChatMessageDto } from "../lib/types";
import { useI18n } from "../lib/i18n";
import { ActionBar, type ActionKey } from "./ActionBar";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { CreditMemoPanel } from "./CreditMemoPanel";
import { Button, Card } from "./ui";

const SUGGESTION_KEYS = [
  "chat.suggestion.dscr",
  "chat.suggestion.collateral",
  "chat.suggestion.conflict",
  "chat.suggestion.summary",
];

export function ChatTab({
  caseId,
  requestedAmountVnd,
  canDecide,
  caseState,
  hasDecision,
  onAction,
}: {
  caseId: string;
  requestedAmountVnd: number | null;
  canDecide: boolean;
  caseState: string;
  hasDecision: boolean;
  onAction: (action: ActionKey, reason?: string) => void;
}) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<ChatMessageDto[] | null>(null);
  const [draft, setDraft] = useState("");
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [memoReady, setMemoReady] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChatMessages(caseId).then(setMessages).catch(() => setMessages([]));
  }, [caseId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, streamingText]);

  const send = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setDraft("");
    setStreamingText("");
    try {
      await sendChatMessage(caseId, trimmed, (chunk) => setStreamingText((prev) => (prev ?? "") + chunk));
    } finally {
      const finalMessages = await fetchChatMessages(caseId).catch(() => null);
      if (finalMessages) setMessages(finalMessages);
      setStreamingText(null);
      setSending(false);
    }
  };

  const shownMessages = (messages ?? []).filter((m) => m.role !== "SYSTEM");
  const isEmpty = messages !== null && shownMessages.length === 0 && streamingText === null;

  return (
    <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1fr_340px]">
      <Card className="flex flex-col p-0" style={{ height: 640 }}>
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages === null ? (
            <p className="text-sm" style={{ color: "var(--text-muted-2)" }}>
              {t("chat.loading")}
            </p>
          ) : isEmpty ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <Sparkles size={22} style={{ color: "var(--brand)" }} />
              <p className="max-w-xs text-sm" style={{ color: "var(--text-muted-2)" }}>
                {t("chat.emptyHint")}
              </p>
            </div>
          ) : (
            <>
              {shownMessages.map((m) => (
                <ChatMessageBubble
                  key={m.message_id}
                  role={m.role as "USER" | "ASSISTANT"}
                  content={m.content}
                  timestamp={m.created_at}
                />
              ))}
              {streamingText !== null && <ChatMessageBubble role="ASSISTANT" content={streamingText} streaming />}
            </>
          )}
        </div>

        {isEmpty && (
          <div className="flex flex-wrap gap-1.5 border-t p-3" style={{ borderColor: "var(--border-hairline)" }}>
            {SUGGESTION_KEYS.map((key) => (
              <button
                key={key}
                onClick={() => send(t(key))}
                className="rounded-full border px-2.5 py-1 text-xs"
                style={{ borderColor: "var(--border-hairline)", color: "var(--text-secondary)" }}
              >
                {t(key)}
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2 border-t p-3" style={{ borderColor: "var(--border-hairline)" }}>
          <input
            className="flex-1 rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: "var(--border-hairline)", background: "var(--surface-1)", color: "var(--text-primary)" }}
            placeholder={t("chat.inputPlaceholder")}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
            disabled={sending}
          />
          <Button variant="primary" onClick={() => send(draft)} disabled={!draft.trim() || sending}>
            <Send size={15} />
          </Button>
        </div>
      </Card>

      <div className="space-y-4">
        <CreditMemoPanel caseId={caseId} canGenerate={hasDecision} onMemoReady={setMemoReady} />
        <ActionBar
          requestedAmountVnd={requestedAmountVnd}
          canDecide={canDecide}
          caseState={caseState}
          memoReady={memoReady}
          onAction={onAction}
        />
      </div>
    </div>
  );
}
