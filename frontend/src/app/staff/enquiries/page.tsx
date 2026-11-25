"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { usd } from "@/components/catalog/ui";
import { useStaff } from "@/components/staff/StaffShell";
import { FlagChips, INFO_FLAGS, StatusBadge } from "@/components/staff/bits";
import { ApiError } from "@/lib/api";
import { type EnquiryRow, KIND_LABELS, STATUSES, type Status, staffApi, when } from "@/lib/staff-api";

export default function EnquiriesPage() {
  const { signedOut } = useStaff();
  const [status, setStatus] = useState<Status | undefined>(undefined);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [rows, setRows] = useState<EnquiryRow[] | null>(null);
  const [counts, setCounts] = useState<Record<Status, number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await staffApi.list({ status, flagged: flaggedOnly });
      setRows(res.enquiries);
      setCounts(res.counts);
    } catch (err) {
      if (!signedOut(err)) setError(err instanceof ApiError ? err.message : "Couldn't load enquiries.");
    }
  }, [status, flaggedOnly, signedOut]);

  useEffect(() => {
    load();
  }, [load]);

  const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : null;
  const tab = (value: Status | undefined, label: string, n: number | null) => (
    <button
      key={label}
      type="button"
      onClick={() => setStatus(value)}
      aria-pressed={status === value}
      className={`shrink-0 rounded-button border px-3 py-1.5 text-brand-xs font-semibold capitalize transition-colors ${
        status === value ? "border-ink bg-ink text-brand-white" : "border-line bg-surface hover:border-ink"
      }`}
    >
      {label}
      {n !== null && <span className="ml-1 opacity-70">{n}</span>}
    </button>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-brand-xl font-bold">Enquiries</h1>
          <p className="text-brand-sm text-muted">Every quote and request from Mira. Flagged ones need a person first.</p>
        </div>
        <button type="button" onClick={load} className="text-brand-xs font-semibold underline underline-offset-2">
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {tab(undefined, "All", total)}
          {STATUSES.map((s) => tab(s, s, counts?.[s] ?? null))}
        </div>
        <label className="ml-auto flex items-center gap-2 text-brand-sm">
          <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)}
                 className="h-4 w-4 accent-brand-orange" />
          Flagged only
        </label>
      </div>

      {error && <p role="alert" className="text-brand-sm text-accent-coral">{error}</p>}
      {rows === null && !error && <p className="text-brand-sm text-muted">Loading…</p>}
      {rows?.length === 0 && <p className="text-brand-sm text-muted">No enquiries here.</p>}

      {rows && rows.length > 0 && (
        <ul className="flex flex-col gap-2">
          {rows.map((r) => (
            <li key={r.id}>
              <Link
                href={`/staff/enquiries/${r.id}`}
                className={`grid gap-2 rounded-card border bg-surface p-3 transition-colors hover:border-ink sm:grid-cols-[1fr_auto] ${
                  r.flagged ? "border-l-4 border-line border-l-accent-coral" : "border-line"
                }`}
              >
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={r.status} />
                    <span className="text-brand-sm font-semibold">{KIND_LABELS[r.kind] ?? r.kind}</span>
                    <span className="text-brand-xs text-muted">{when(r.created_at)}</span>
                  </div>
                  <p className="truncate text-brand-sm">
                    {r.tour_name ? `${r.tour_id} · ${r.tour_name}` : "No tour chosen"}
                    {r.start_date && <span className="text-muted"> · from {r.start_date}</span>}
                  </p>
                  <FlagChips flags={r.flags} info={INFO_FLAGS} />
                </div>
                <div className="flex items-center gap-3 text-brand-sm sm:flex-col sm:items-end sm:justify-center">
                  <span className="font-semibold">{r.price_usd !== null ? usd(r.price_usd) : "No price"}</span>
                  <span className="text-brand-xs text-muted">
                    {r.contact_name ?? "No contact yet"}
                    {r.note_count > 0 && ` · ${r.note_count} note${r.note_count > 1 ? "s" : ""}`}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
