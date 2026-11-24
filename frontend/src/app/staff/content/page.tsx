"use client";

import { useCallback, useEffect, useState } from "react";

import { useStaff } from "@/components/staff/StaffShell";
import { Panel } from "@/components/staff/bits";
import { ApiError } from "@/lib/api";
import { type ContentDetail, type ContentStatus, type ContentSummary, contentApi, mediaUrl, when } from "@/lib/staff-api";

const EXAMPLE = "Add a 5-day Hill Country tour using the Ella photos";

const STATUS_LOOK: Record<ContentStatus, string> = {
  draft: "bg-accent-sun/30 text-ink",
  published: "bg-accent-leaf/30 text-ink",
  rejected: "bg-line text-muted",
};

function Badge({ status }: { status: ContentStatus }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-brand-xs font-semibold capitalize ${STATUS_LOOK[status]}`}>
      {status}
    </span>
  );
}

/** R8: staff ask the content agent for a draft; only an approver can publish it. */
export default function ContentPage() {
  const { me, signedOut } = useStaff();
  const [items, setItems] = useState<ContentSummary[] | null>(null);
  const [selected, setSelected] = useState<ContentDetail | null>(null);
  const [command, setCommand] = useState("");
  const [busy, setBusy] = useState<"draft" | "publish" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const isApprover = me.role === "approver";

  const fail = useCallback(
    (err: unknown, fallback: string) => {
      if (!signedOut(err)) setError(err instanceof ApiError ? err.message : fallback);
    },
    [signedOut],
  );

  const load = useCallback(async () => {
    try {
      setItems(await contentApi.list());
    } catch (err) {
      fail(err, "Couldn't load content.");
    }
  }, [fail]);

  useEffect(() => {
    load();
  }, [load]);

  async function open(id: string) {
    setError(null);
    try {
      setSelected(await contentApi.get(id));
    } catch (err) {
      fail(err, "Couldn't open that item.");
    }
  }

  async function draft(e: React.FormEvent) {
    e.preventDefault();
    if (command.trim().length < 5) return;
    setBusy("draft");
    setError(null);
    try {
      const item = await contentApi.create(command.trim());
      setSelected(item);
      setCommand("");
      await load();
    } catch (err) {
      fail(err, "The draft couldn't be created.");
    } finally {
      setBusy(null);
    }
  }

  async function act(kind: "publish" | "reject") {
    if (!selected) return;
    setBusy(kind);
    setError(null);
    try {
      setSelected(kind === "publish" ? await contentApi.publish(selected.id) : await contentApi.reject(selected.id, note));
      setNote("");
      await load();
    } catch (err) {
      fail(err, kind === "publish" ? "Couldn't publish." : "Couldn't reject.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-brand-xl font-bold">Content</h1>
        <p className="text-brand-sm text-muted">
          Ask for a new tour page. Mira&apos;s content agent writes a draft from our published pages only; an approver
          reviews and publishes it. Drafts are never shown to travellers.
        </p>
      </div>

      <form onSubmit={draft} className="flex flex-col gap-2 rounded-card border border-line bg-surface p-4">
        <label htmlFor="command" className="text-brand-sm font-semibold">
          What should the agent write?
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            id="command"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder={EXAMPLE}
            maxLength={500}
            className="min-w-0 flex-1 rounded-button border border-line px-3 py-2 text-brand-sm focus-visible:outline-2 focus-visible:outline-brand-orange"
          />
          <button
            type="submit"
            disabled={busy !== null || command.trim().length < 5}
            className="rounded-button bg-brand-orange px-4 py-2 text-brand-sm font-semibold text-ink disabled:opacity-50"
          >
            {busy === "draft" ? "Drafting…" : "Create draft"}
          </button>
        </div>
        <button
          type="button"
          onClick={() => setCommand(EXAMPLE)}
          className="self-start text-brand-xs text-muted underline underline-offset-2"
        >
          Use the example
        </button>
        {busy === "draft" && (
          <p className="text-brand-xs text-muted" role="status">
            Planning, writing from our pages and checking the draft. This takes up to a minute.
          </p>
        )}
      </form>

      {error && (
        <p role="alert" className="rounded-card border border-accent-coral bg-surface px-4 py-3 text-brand-sm">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Panel title="Items">
          {items === null ? (
            <p className="text-brand-sm text-muted">Loading…</p>
          ) : items.length === 0 ? (
            <p className="text-brand-sm text-muted">No content yet. Create the first draft above.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-line">
              {items.map((i) => (
                <li key={i.id}>
                  <button
                    type="button"
                    onClick={() => open(i.id)}
                    aria-current={selected?.id === i.id ? "true" : undefined}
                    className={`flex w-full flex-col gap-1 px-2 py-2 text-left hover:bg-[#F7F7F5] ${
                      selected?.id === i.id ? "bg-[#F7F7F5]" : ""
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-brand-sm font-semibold">{i.title}</span>
                      <Badge status={i.status} />
                    </span>
                    <span className="text-brand-xs text-muted">
                      {i.days ? `${i.days} days · ` : ""}
                      {i.doc_id ? `${i.doc_id} · ` : ""}
                      {i.created_by} · {when(i.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title={selected ? "Preview" : "Preview"}
          aside={selected ? <Badge status={selected.status} /> : undefined}
        >
          {!selected ? (
            <p className="text-brand-sm text-muted">Choose an item to preview it.</p>
          ) : (
            <article className="flex flex-col gap-3">
              <div>
                <h3 className="text-brand-lg font-bold">{selected.title}</h3>
                <p className="text-brand-xs text-muted">
                  {selected.days} days · {selected.places.join(", ")} · asked: “{selected.command}”
                </p>
              </div>
              {selected.media.length > 0 && (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {selected.media.map((m) => (
                    // eslint-disable-next-line @next/next/no-img-element -- our own small SVG illustrations
                    <img
                      key={m.id}
                      src={mediaUrl(m.url)}
                      alt={m.alt}
                      className="aspect-[4/3] w-full rounded-card border border-line bg-[#F7F7F5] object-cover"
                    />
                  ))}
                </div>
              )}
              <p className="text-brand-sm">{selected.overview}</p>
              <ol className="flex flex-col gap-2">
                {selected.itinerary.map((d) => (
                  <li key={d.day} className="rounded-card border border-line p-3">
                    <p className="text-brand-sm font-semibold">
                      Day {d.day}: {d.title}
                    </p>
                    <p className="text-brand-sm">{d.description}</p>
                  </li>
                ))}
              </ol>
              <p className="text-brand-xs text-muted">
                Written from: {selected.sources.join(", ") || "none"}. No prices: a published tour has no rate yet, so
                Mira hands price requests to a specialist.
              </p>
              {selected.review_note && <p className="text-brand-sm">Review note: {selected.review_note}</p>}
              {selected.status === "published" && (
                <p className="text-brand-sm" role="status">
                  Published as {selected.doc_id}
                  {selected.approved_by ? ` by ${selected.approved_by}` : ""}.{" "}
                  {selected.indexed === false
                    ? "Search will include it after the next restart."
                    : "Mira can answer questions about it now."}
                </p>
              )}

              {selected.status === "draft" &&
                (isApprover ? (
                  <div className="flex flex-col gap-2 border-t border-line pt-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => act("publish")}
                        disabled={busy !== null}
                        className="rounded-button bg-brand-orange px-4 py-2 text-brand-sm font-semibold text-ink disabled:opacity-50"
                      >
                        {busy === "publish" ? "Publishing…" : "Publish"}
                      </button>
                      <button
                        type="button"
                        onClick={() => act("reject")}
                        disabled={busy !== null}
                        className="rounded-button border border-line px-4 py-2 text-brand-sm font-semibold hover:border-ink disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                    <label className="flex flex-col gap-1 text-brand-xs text-muted">
                      Note (for a rejection)
                      <input
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        maxLength={500}
                        className="rounded-button border border-line px-3 py-1.5 text-brand-sm text-ink"
                      />
                    </label>
                  </div>
                ) : (
                  <p className="border-t border-line pt-3 text-brand-sm text-muted">
                    Only an approver can publish or reject this draft.
                  </p>
                ))}
            </article>
          )}
        </Panel>
      </div>
    </div>
  );
}
