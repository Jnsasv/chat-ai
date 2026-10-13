export type ChatStatus =
  | "answered"
  | "clarification_required"
  | "unsupported"
  | "insufficient_data";

export interface ChatSource {
  query_id: string;
  label: string;
  urls: string[];
}

export interface ChatMessageResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  status: ChatStatus;
  sources: ChatSource[];
}

export class ChatApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ChatApiError";
  }
}

const CHAT_STATUSES: ReadonlySet<string> = new Set([
  "answered",
  "clarification_required",
  "unsupported",
  "insufficient_data",
]);
const OFFICIAL_SOURCE_DOMAINS = ["fifa.com", "fifatrainingcentre.com"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isChatStatus(value: unknown): value is ChatStatus {
  return typeof value === "string" && CHAT_STATUSES.has(value);
}

function isChatSource(value: unknown): value is ChatSource {
  return (
    isRecord(value) &&
    typeof value.query_id === "string" &&
    typeof value.label === "string" &&
    Array.isArray(value.urls) &&
    value.urls.every((url) => typeof url === "string")
  );
}

function isOfficialSourceUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase().replace(/\.$/, "");
    return (
      url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      (url.port === "" || url.port === "443") &&
      OFFICIAL_SOURCE_DOMAINS.some(
        (domain) => hostname === domain || hostname.endsWith(`.${domain}`),
      )
    );
  } catch {
    return false;
  }
}

function parseChatMessageResponse(value: unknown): ChatMessageResponse {
  if (
    !isRecord(value) ||
    typeof value.conversation_id !== "string" ||
    typeof value.message_id !== "string" ||
    typeof value.answer !== "string" ||
    !isChatStatus(value.status) ||
    !Array.isArray(value.sources) ||
    !value.sources.every(isChatSource)
  ) {
    throw new ChatApiError("The server returned an invalid chat response.", 502);
  }
  return {
    conversation_id: value.conversation_id,
    message_id: value.message_id,
    answer: value.answer,
    status: value.status,
    sources: value.sources,
  };
}

function safeErrorMessage(status: number | null): string {
  if (status === 422) {
    return "Please enter a valid question about the supported tournament data.";
  }
  if (status === 503) {
    return "Chat is not available yet. Please try again later.";
  }
  if (status === 502 || status === 504) {
    return "The request could not be completed. Please try again later.";
  }
  return "Unable to connect to Data Chat. Please try again.";
}

export async function postChatMessage(
  message: string,
  conversationId: string | null,
): Promise<ChatMessageResponse> {
  let response: Response;
  try {
    response = await fetch("/api/v1/chat/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });
  } catch {
    throw new ChatApiError(safeErrorMessage(null), null);
  }

  if (!response.ok) {
    throw new ChatApiError(safeErrorMessage(response.status), response.status);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ChatApiError("The server returned an invalid chat response.", 502);
  }
  const result = parseChatMessageResponse(body);
  return {
    ...result,
    sources: result.sources.map((source) => ({
      ...source,
      urls: source.urls.filter(isOfficialSourceUrl),
    })),
  };
}
