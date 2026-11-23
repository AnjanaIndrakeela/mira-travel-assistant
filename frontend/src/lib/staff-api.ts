// Staff console calls (Phase 13). The session is an HttpOnly cookie set by the backend, so
// every call sends credentials; the browser never sees or stores the token itself.

import { call } from "./api";

export const STATUSES = ["new", "contacted", "pending", "confirmed", "closed"] as const;
export type Status = (typeof STATUSES)[number];

export type Me = { email: string; role: "staff" | "approver" };

export type EnquiryRow = {
  id: string;
  kind: string;
  status: Status;
  flagged: boolean;
  flags: string[];
  created_at: string;
  tour_id: string | null;
  tour_name: string | null;
  start_date: string | null;
  price_usd: number | null;
  contact_name: string | null;
  note_count: number;
};

export type CostLine = { item: string; detail?: string; lkr?: string; usd?: string };

export type StaffQuote = {
  id: string;
  status: "ok" | "needs_specialist";
  tour_id: string;
  tour_name: string | null;
  start_date: string;
  end_date: string | null;
  adults: number;
  child_ages: number[];
  price_usd: number | null;
  deposit_usd: number | null;
  balance_usd: number | null;
  balance_due: string | null;
  cost_usd: string | null;
  cost_lkr: string | null;
  fx_lkr_per_usd: string | null;
  margin: string | null;
  gp_pct: string | null;
  vehicle: string | null;
  cost_lines: CostLine[] | null;
  reasons: { code: string; detail_staff?: string; message_traveller?: string }[];
};

export type Note = { id: string; body: string; author: string; created_at: string };

export type EnquiryDetail = {
  id: string;
  kind: string;
  status: Status;
  flagged: boolean;
  flags: string[];
  created_at: string;
  updated_at: string;
  contact: { name?: string; email?: string; phone?: string | null } | null;
  traveller_notes: string | null;
  quote: StaffQuote | null;
  trace_id: string | null;
  trace_url: string | null;
  conversation_id: string | null;
  conversation: { role: "traveller" | "mira"; text: string }[];
  notes: Note[];
};

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  credentials: "include",
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

export const staffApi = {
  login: (email: string, password: string) => call<Me>("/auth/login", send("POST", { email, password }), 15_000),
  logout: () => call<null>("/auth/logout", send("POST"), 10_000),
  me: () => call<Me>("/auth/me", send("GET"), 10_000),
  list: (filter: { status?: Status; flagged?: boolean }) => {
    const q = new URLSearchParams();
    if (filter.status) q.set("status", filter.status);
    if (filter.flagged) q.set("flagged", "true");
    const qs = q.toString();
    return call<{ enquiries: EnquiryRow[]; counts: Record<Status, number> }>(
      `/staff/enquiries${qs ? `?${qs}` : ""}`, send("GET"), 15_000);
  },
  get: (id: string) => call<EnquiryDetail>(`/staff/enquiries/${encodeURIComponent(id)}`, send("GET"), 20_000),
  addNote: (id: string, body: string) =>
    call<Note>(`/staff/enquiries/${encodeURIComponent(id)}/notes`, send("POST", { body }), 15_000),
  setStatus: (id: string, status: Status) =>
    call<EnquiryRow>(`/staff/enquiries/${encodeURIComponent(id)}/status`, send("PATCH", { status }), 15_000),
};

export const KIND_LABELS: Record<string, string> = {
  quote: "Quote",
  no_price: "No price",
  custom: "Custom request",
  booking_failed: "Payment failed",
};

export const FLAG_LABELS: Record<string, string> = {
  no_price: "No price",
  missing_rate: "Missing rate",
  expired_rate: "Expired rate",
  rate_conflict: "Rate conflict",
  handoff_requested: "Handoff",
  card_declined: "Card declined",
  unanswered_question: "Unanswered question",
  llm_unavailable: "AI unavailable",
  from_traveller: "From traveller",
  direct_quote: "Direct quote",
};

export const flagLabel = (f: string) => FLAG_LABELS[f] ?? f.replace(/_/g, " ");

export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
