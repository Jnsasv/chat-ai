import { useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { ChatApiError, postChatMessage } from "./api/chat";
import type { ChatMessageResponse } from "./api/chat";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: ChatMessageResponse["status"];
  sources?: ChatMessageResponse["sources"];
}

const STATUS_LABELS: Record<ChatMessageResponse["status"], string> = {
  answered: "Answered",
  clarification_required: "Needs clarification",
  unsupported: "Outside supported topics",
  insufficient_data: "Not enough data",
};

function createMessageId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || isPending) return;

    setDraft("");
    setError(null);
    setMessages((current) => [
      ...current,
      { id: createMessageId(), role: "user", text: question },
    ]);
    setIsPending(true);

    try {
      const response = await postChatMessage(question, conversationId);
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          text: response.answer,
          status: response.status,
          sources: response.sources,
        },
      ]);
    } catch (requestError) {
      setError(
        requestError instanceof ChatApiError
          ? requestError.message
          : "Unable to complete the request. Please try again.",
      );
    } finally {
      setIsPending(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <main className="page-shell">
      <section className="chat-panel" aria-labelledby="page-title">
        <header className="page-header">
          <div className="brand-mark" aria-hidden="true">
            DC
          </div>
          <div>
            <p className="eyebrow">DATA CHAT</p>
            <h1 id="page-title">World Cup 2026 assistant</h1>
            <p className="subtitle">
              Ask about teams, venues, matches, results and standings.
            </p>
          </div>
        </header>

        <div className="conversation" aria-live="polite" aria-busy={isPending}>
          {messages.length === 0 && (
            <div className="welcome-card">
              <p className="welcome-icon" aria-hidden="true">
                26
              </p>
              <h2>What would you like to know?</h2>
              <p>
                Responses use only approved database queries. This local demo
                includes synthetic records, clearly labeled as not official FIFA
                information.
              </p>
              <div className="suggestions" aria-label="Example questions">
                <span>Show the group standings</span>
                <span>Where did a team play?</span>
                <span>What was the match result?</span>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <article
              className={`message message-${message.role}`}
              key={message.id}
              aria-label={message.role === "user" ? "Your question" : "Assistant response"}
            >
              {message.role === "assistant" && (
                <div className="message-meta">
                  <span>Data Chat</span>
                  {message.status && (
                    <span className={`status-pill status-${message.status}`}>
                      {STATUS_LABELS[message.status]}
                    </span>
                  )}
                </div>
              )}
              <p>{message.text}</p>
              {message.sources?.map((source) => {
                return (
                  <div className="source-list" key={source.query_id}>
                    <span>{source.label}</span>
                    {source.urls.map((url) => (
                      <a
                        href={url}
                        key={url}
                        rel="noreferrer noopener"
                        target="_blank"
                      >
                        Official source
                      </a>
                    ))}
                  </div>
                );
              })}
            </article>
          ))}

          {isPending && (
            <p className="pending-message" role="status">
              Checking the approved data…
            </p>
          )}
          {error && (
            <div className="error-message" role="alert">
              {error}
            </div>
          )}
        </div>

        <form className="composer" onSubmit={submitMessage}>
          <label className="sr-only" htmlFor="question">
            Ask about World Cup 2026
          </label>
          <textarea
            id="question"
            ref={textareaRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={2000}
            placeholder="Ask a question about the tournament…"
            rows={2}
            disabled={isPending}
          />
          <div className="composer-footer">
            <span className="input-hint">Enter to send · Shift+Enter for a new line</span>
            <span className="character-count">{draft.length}/2000</span>
            <button type="submit" disabled={!draft.trim() || isPending}>
              {isPending ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
        <footer className="privacy-note">
          Demo records are synthetic, not official FIFA data. Do not enter private information.
        </footer>
      </section>
    </main>
  );
}
