// Talks to the Mira backend. Keeps the conversation and visitor IDs in localStorage (wrapped
// in try/catch: storage can be blocked or full), and turns every failure into friendly text.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");

export type Source = { n: number; doc_id: string; title: string; section: string };
export type UIComponent = { type: string; [key: string]: unknown };

export type ChatResponse = {
  conversation_id: string;
  visitor_id: string;
  message: string;
  ui: UIComponent[];
  sources: Source[];
  quote_id: string | null;
  enquiry_id: string | null;
};

export class ApiError extends Error {
  constructor(message: string, readonly retryable: boolean) {
    super(message);
  }
}

const KEYS = { conversation: "mira.conversation_id", visitor: "mira.visitor_id" } as const;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the chat still works, it just won't be remembered */
  }
}

export const ids = {
  conversation: () => read(KEYS.conversation),
  visitor: () => read(KEYS.visitor),
  /** Start a new conversation; the visitor ID is kept (R2: returning visitors). */
  startOver: () => write(KEYS.conversation, null),
};

const OFFLINE = "I can't reach our server right now. Please check your connection and try again.";
const BUSY = "Something went wrong on our side. Please try again in a moment.";

async function call<T>(path: string, init: RequestInit, timeoutMs = 60_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(OFFLINE, true);
  } finally {
    clearTimeout(timer);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* not JSON: fall through to the generic message */
  }
  if (!res.ok) {
    const message =
      body && typeof body === "object" && "message" in body && typeof body.message === "string"
        ? body.message
        : BUSY;
    throw new ApiError(message, res.status >= 500 || res.status === 429);
  }
  return body as T;
}

export async function sendChat(message: string): Promise<ChatResponse> {
  const payload: Record<string, string> = { message };
  const conversation = ids.conversation();
  const visitor = ids.visitor();
  if (conversation) payload.conversation_id = conversation;
  if (visitor) payload.visitor_id = visitor;
  const res = await call<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(payload) });
  write(KEYS.conversation, res.conversation_id);
  write(KEYS.visitor, res.visitor_id);
  return res;
}

export type HistoryMessage = { role: "traveller" | "mira"; text: string };

/** The current conversation's messages, or [] if there is none (or the server forgot it). */
export async function loadHistory(): Promise<HistoryMessage[]> {
  const conversation = ids.conversation();
  if (!conversation) return [];
  try {
    const res = await call<{ messages: HistoryMessage[] }>(`/conversations/${conversation}`, { method: "GET" }, 10_000);
    return res.messages;
  } catch {
    return [];
  }
}
