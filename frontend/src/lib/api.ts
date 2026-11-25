// Talks to the Mira backend. Keeps the conversation and visitor IDs in localStorage (wrapped
// in try/catch: storage can be blocked or full), and turns every failure into friendly text.

// "http://localhost:8000" and "http://localhost:8000/api/v1" both work: the version path is added if missing.
const BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");
export const API_URL = BASE.endsWith("/api/v1") ? BASE : `${BASE}/api/v1`;
/** Full URL of a file our media route serves ("/api/v1/media/ella/x.jpg"). */
export const mediaUrl = (path: string) => API_URL.replace(/\/api\/v1$/, "") + path;

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
  constructor(message: string, readonly retryable: boolean, readonly status?: number) {
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
  /** Open a chat from the link in a specialist's email (?chat=<id>), on any device. */
  openConversation: (id: string) => {
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) write(KEYS.conversation, id);
  },
  /** "Start fresh": forget this browser's visitor too, so nothing from last time is reused. */
  forgetVisitor: () => {
    write(KEYS.conversation, null);
    write(KEYS.visitor, null);
  },
};

const OFFLINE = "I can't reach our server right now. Please check your connection and try again.";
const BUSY = "Something went wrong on our side. Please try again in a moment.";

export async function call<T>(path: string, init: RequestInit, timeoutMs = 60_000): Promise<T> {
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
    throw new ApiError(message, res.status >= 500 || res.status === 429, res.status);
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

/** One message of the saved chat; Mira's replies carry the cards shown with them. A
 * "specialist" message is a person on the team, shown exactly as they wrote it. */
export type HistoryMessage = { role: "traveller" | "mira" | "specialist"; text: string; ui?: UIComponent[] };

/** The current conversation's messages (kept in the server's database), or [] if there is none. */
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

export type Welcome = { message: string; ui: UIComponent[]; quote_id: string | null; status: string };

/** R2: a returning visitor's welcome, with the last quote re-priced today (null for a new visitor). */
export async function loadWelcome(): Promise<Welcome | null> {
  const visitor = ids.visitor();
  if (!visitor || ids.conversation()) return null;
  try {
    return await call<Welcome | null>(`/visitors/${visitor}/welcome`, { method: "GET" }, 10_000);
  } catch {
    return null;
  }
}

// ---- Phase 11: the event stream, quotes, bookings, enquiries --------------------------------

/** Shown from the moment a message is sent (the first step reads it). */
export const FIRST_STEP = "Reading your message";

/** What Mira is doing AFTER each graph step the stream reports as finished. */
export const STEP_LABELS: Record<string, string> = {
  load_visitor: "Reading your message",
  guard: "Working out what you need",
  discovery: "Working out what you need",
  route: "Looking into it",
  retrieve: "Checked our pages, writing a reply",
  price: "Priced from our rate sheet, writing a reply",
  match_tours: "Found tours that fit, writing a reply",
  respond: "Almost there",
  persist: "Almost there",
  build_ui: "Almost there",
};

/**
 * One turn over the AG-UI-style SSE stream (POST /chat/stream). `onStep` gets each finished
 * graph node; the promise resolves with the same ChatResponse as POST /chat.
 */
export async function streamChat(message: string, onStep: (step: string) => void): Promise<ChatResponse> {
  const payload: Record<string, string> = { message };
  const conversation = ids.conversation();
  const visitor = ids.visitor();
  if (conversation) payload.conversation_id = conversation;
  if (visitor) payload.visitor_id = visitor;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120_000);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch {
    clearTimeout(timer);
    throw new ApiError(OFFLINE, true);
  }
  if (!res.ok || !res.body) {
    clearTimeout(timer);
    let msg = BUSY;
    try {
      const body = await res.json();
      if (typeof body?.message === "string") msg = body.message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(msg, res.status >= 500 || res.status === 429);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResponse | null = null;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut: number;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const data = frame
          .split("\n")
          .filter((l) => l.startsWith("data: "))
          .map((l) => l.slice(6))
          .join("\n");
        if (!data) continue;
        let event: { type?: string; stepName?: string; result?: ChatResponse; message?: string };
        try {
          event = JSON.parse(data);
        } catch {
          continue;
        }
        if (event.type === "STEP_FINISHED" && event.stepName) onStep(event.stepName);
        else if (event.type === "RUN_FINISHED" && event.result) result = event.result;
        else if (event.type === "RUN_ERROR") throw new ApiError(event.message || BUSY, true);
      }
    }
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(OFFLINE, true);
  } finally {
    clearTimeout(timer);
  }
  if (!result) throw new ApiError(BUSY, true);
  write(KEYS.conversation, result.conversation_id);
  write(KEYS.visitor, result.visitor_id);
  return result;
}

/** The verified public quote: the only place a price on screen comes from. */
export type PublicQuote = {
  tour_id: string;
  tour_name: string;
  start_date: string;
  end_date: string;
  adults: number;
  children: number;
  infants: number;
  price_usd: number;
  deposit_usd: number;
  balance_usd: number;
  balance_due: string | null;
  currency: "USD";
};

export function getQuote(quoteId: string): Promise<unknown> {
  return call<unknown>(`/quotes/${encodeURIComponent(quoteId)}`, { method: "GET" }, 15_000);
}

export type Contact = { name: string; email: string; phone?: string };

export type BookingResult = {
  status: "confirmed" | "payment_failed" | "price_changed";
  message: string;
  booking_id: string | null;
  payment_reference: string | null;
  amount_charged_usd: number | null;
  next_steps: ("retry" | "payment_link" | "enquiry_saved" | "new_quote")[];
  enquiry_id: string | null;
  /** The card detail the server asks to fix. */
  field: "holder" | "brand" | "number" | "expiry" | "cvc" | null;
  /** "Visa ending 4242" on a confirmed booking. */
  card: string | null;
};

export type CardPayload = {
  holder: string;
  brand: "visa" | "mastercard" | "amex";
  number: string;
  exp_month: number;
  exp_year: number;
  cvc: string;
};

/** Straight from the form to the API: never through the chat, the LLM or the traces. */
export function book(quoteId: string, contact: Contact, card: CardPayload): Promise<BookingResult> {
  return call<BookingResult>("/bookings", {
    method: "POST",
    body: JSON.stringify({ quote_id: quoteId, contact, card }),
  });
}

export function sendEnquiry(input: {
  kind: "custom" | "quote" | "no_price";
  notes?: string;
  quote_id?: string;
  contact?: Contact;
}): Promise<{ enquiry_id: string; message: string }> {
  const conversation = ids.conversation();
  return call("/enquiries", {
    method: "POST",
    body: JSON.stringify({ ...input, ...(conversation ? { conversation_id: conversation } : {}) }),
  });
}
