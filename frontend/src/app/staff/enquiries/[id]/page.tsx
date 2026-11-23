"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { niceDate, Pill, usd } from "@/components/catalog/ui";
import { useStaff } from "@/components/staff/StaffShell";
import { FlagChips, INFO_FLAGS, Panel, StatusBadge } from "@/components/staff/bits";
import { ApiError } from "@/lib/api";
import { type EnquiryDetail, KIND_LABELS, STATUSES, type Status, staffApi, when } from "@/lib/staff-api";

const num = (v: string | null, digits = 2) =>
  v === null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-1.5 text-brand-sm last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-semibold">{children}</dd>
    </div>
  );
}

export default function EnquiryPage() {
  const { id } = useParams<{ id: string }>();
  const { signedOut } = useStaff();
  const [e, setE] = useState<EnquiryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setE(await staffApi.get(id));
    } catch (err) {
      if (!signedOut(err)) setError(err instanceof ApiError ? err.message : "Couldn't load this enquiry.");
    }
  }, [id, signedOut]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      await load();
      return true;
    } catch (err) {
      if (!signedOut(err)) setActionError(err instanceof ApiError ? err.message : "That didn't work. Please try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function addNote(ev: React.FormEvent) {
    ev.preventDefault();
    if (await act(() => staffApi.addNote(id, note.trim()))) setNote("");
  }

  if (error) return <p role="alert" className="text-brand-sm text-accent-coral">{error}</p>;
  if (!e) return <p className="text-brand-sm text-muted">Loading…</p>;
  const q = e.quote;
  const party = q ? `${q.adults} adult${q.adults > 1 ? "s" : ""}${q.child_ages.length ? `, children aged ${q.child_ages.join(", ")}` : ""}` : null;

  return (
    <div className="flex flex-col gap-4">
      <Link href="/staff/enquiries" className="text-brand-xs font-semibold underline underline-offset-2">
        ← All enquiries
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-brand-xl font-bold">
            {KIND_LABELS[e.kind] ?? e.kind}
            {q?.tour_name && <span className="font-normal"> · {q.tour_name}</span>}
          </h1>
          <p className="text-brand-xs text-muted">
            Received {when(e.created_at)} · Enquiry {e.id.slice(0, 8)}
          </p>
          <FlagChips flags={e.flags} info={INFO_FLAGS} />
        </div>
        <label className="flex items-center gap-2 text-brand-sm">
          <span className="font-semibold">Status</span>
          <StatusBadge status={e.status} />
          <select
            value={e.status}
            disabled={busy}
            onChange={(ev) => act(() => staffApi.setStatus(id, ev.target.value as Status))}
            className="rounded-input border border-line bg-surface px-2 py-1.5 text-brand-sm capitalize"
            aria-label="Change status"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      {actionError && <p role="alert" className="text-brand-sm text-accent-coral">{actionError}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Traveller">
          <dl>
            <Row label="Name">{e.contact?.name ?? "Not given yet"}</Row>
            <Row label="Email">
              {e.contact?.email ? <a className="underline" href={`mailto:${e.contact.email}`}>{e.contact.email}</a> : "—"}
            </Row>
            {e.contact?.phone && <Row label="Phone">{e.contact.phone}</Row>}
            {party && <Row label="Party">{party}</Row>}
          </dl>
          {e.traveller_notes && (
            <p className="mt-3 whitespace-pre-wrap rounded-input bg-[#F7F7F5] p-3 text-brand-sm">{e.traveller_notes}</p>
          )}
        </Panel>

        <Panel
          title="Quote"
          aside={e.trace_url ? (
            <a href={e.trace_url} target="_blank" rel="noopener noreferrer"
               className="text-brand-xs font-semibold underline underline-offset-2">
              Open trace ↗
            </a>
          ) : e.trace_id ? <span className="text-brand-xs text-muted">Trace {e.trace_id.slice(0, 8)}</span> : null}
        >
          {!q ? (
            <p className="text-brand-sm text-muted">No quote: the traveller hasn&apos;t chosen a tour and dates yet.</p>
          ) : (
            <dl>
              <Row label="Tour">{q.tour_id} · {q.tour_name ?? "—"}</Row>
              <Row label="Dates">{niceDate(q.start_date)}{q.end_date && ` – ${niceDate(q.end_date)}`}</Row>
              {q.status === "ok" ? (
                <>
                  <Row label="Price">{usd(q.price_usd ?? 0)}</Row>
                  <Row label="Deposit">{usd(q.deposit_usd ?? 0)}</Row>
                  <Row label="Balance">{usd(q.balance_usd ?? 0)}{q.balance_due && ` by ${niceDate(q.balance_due)}`}</Row>
                  <Row label="Cost">USD {num(q.cost_usd)} <span className="font-normal text-muted">(LKR {num(q.cost_lkr, 0)})</span></Row>
                  <Row label="Gross profit">{num(q.gp_pct)}% <span className="font-normal text-muted">(margin {num(q.margin === null ? null : String(Number(q.margin) * 100), 0)}%)</span></Row>
                  {q.fx_lkr_per_usd && <Row label="FX">{num(q.fx_lkr_per_usd)} LKR per USD</Row>}
                  {q.vehicle && <Row label="Vehicle">{q.vehicle}</Row>}
                </>
              ) : (
                <Row label="Price">Not priced</Row>
              )}
            </dl>
          )}
          {q && q.reasons.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1 text-brand-sm">
              {q.reasons.map((r) => (
                <li key={r.code}>
                  <span className="font-semibold">{r.code.replace(/_/g, " ")}:</span> {r.detail_staff ?? r.message_traveller}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {q?.cost_lines && q.cost_lines.length > 0 && (
        <Panel title="Cost breakdown">
          <div className="overflow-x-auto">
            <table className="w-full text-brand-sm">
              <thead>
                <tr className="text-left text-brand-xs text-muted">
                  <th className="py-1 pr-3 font-semibold">Item</th>
                  <th className="py-1 pr-3 font-semibold">Detail</th>
                  <th className="py-1 pr-3 text-right font-semibold">LKR</th>
                  <th className="py-1 text-right font-semibold">USD</th>
                </tr>
              </thead>
              <tbody>
                {q.cost_lines.map((c, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="py-1.5 pr-3 capitalize">{c.item}</td>
                    <td className="py-1.5 pr-3 text-muted">{c.detail}</td>
                    <td className="py-1.5 pr-3 text-right">{c.lkr && c.lkr !== "0" ? num(c.lkr, 0) : "—"}</td>
                    <td className="py-1.5 text-right">{c.usd && c.usd !== "0" ? num(c.usd) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Notes" aside={<span className="text-brand-xs text-muted">Notes can&apos;t be edited</span>}>
          {e.notes.length === 0 ? (
            <p className="mb-3 text-brand-sm text-muted">No notes yet.</p>
          ) : (
            <ol className="mb-3 flex flex-col gap-2">
              {e.notes.map((n) => (
                <li key={n.id} className="rounded-input bg-[#F7F7F5] p-2.5">
                  <p className="whitespace-pre-wrap text-brand-sm">{n.body}</p>
                  <p className="mt-1 text-brand-xs text-muted">{n.author} · {when(n.created_at)}</p>
                </li>
              ))}
            </ol>
          )}
          <form onSubmit={addNote} className="flex flex-col gap-2">
            <label className="flex flex-col gap-1 text-brand-sm">
              <span className="font-semibold">Add a note</span>
              <textarea
                value={note}
                onChange={(ev) => setNote(ev.target.value)}
                maxLength={4000}
                rows={3}
                required
                className="rounded-input border border-line px-3 py-2 text-brand-md outline-none focus:border-brand-orange"
              />
            </label>
            <div>
              <Pill type="submit" disabled={busy || !note.trim()}>{busy ? "Saving…" : "Add note"}</Pill>
            </div>
          </form>
        </Panel>

        <Panel title="Conversation">
          {e.conversation.length === 0 ? (
            <p className="text-brand-sm text-muted">
              {e.conversation_id ? "The chat isn't in memory any more (the server restarted)." : "No chat linked."}
            </p>
          ) : (
            <ol className="flex max-h-96 flex-col gap-2 overflow-y-auto">
              {e.conversation.map((m, i) => (
                <li key={i} className={`rounded-input p-2.5 text-brand-sm ${m.role === "traveller" ? "ml-6 bg-brand-orange/10" : "mr-6 bg-[#F7F7F5]"}`}>
                  <span className="block text-brand-xs font-semibold text-muted">{m.role === "traveller" ? "Traveller" : "Mira"}</span>
                  <span className="whitespace-pre-wrap">{m.text}</span>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </div>
  );
}
