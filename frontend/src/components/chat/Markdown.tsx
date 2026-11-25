// A tiny, safe Markdown renderer for Mira's replies and tour text: **bold**, *italic* / _italic_,
// `- ` / `* ` / `1. ` lists and paragraphs. It builds React elements only (no HTML strings, no
// dangerouslySetInnerHTML), so nothing in a reply can ever become markup or a script.

import { Fragment, type ReactNode } from "react";

const INLINE = /\*\*(.+?)\*\*|__(.+?)__|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])/g;

/** Bold and italic inside one line. Unmatched asterisks stay as they are. */
export function Inline({ text }: { text: string }): ReactNode {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const [, b1, b2, i1, i2] = m;
    if (b1 ?? b2) out.push(<strong key={k++} className="font-semibold"><Inline text={(b1 ?? b2)!} /></strong>);
    else out.push(<em key={k++}><Inline text={(i1 ?? i2)!} /></em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul" | "ol"; items: string[] };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBER = /^\s*\d{1,2}[.)]\s+(.*)$/;

function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const last = out[out.length - 1];
    const bullet = BULLET.exec(line);
    const number = bullet ? null : NUMBER.exec(line);
    if (bullet || number) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? number)![1];
      if (last?.kind === kind) last.items.push(item);
      else out.push({ kind, items: [item] });
    } else if (!line.trim()) {
      out.push({ kind: "p", lines: [] });          // paragraph break
    } else if (last?.kind === "p" && last.lines.length) {
      last.lines.push(line);
    } else {
      out.push({ kind: "p", lines: [line] });
    }
  }
  return out.filter((b) => (b.kind === "p" ? b.lines.length > 0 : true));
}

/** A whole reply: paragraphs and lists, each line through Inline. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      {blocks(text).map((b, i) =>
        b.kind === "p" ? (
          <p key={i}>
            {b.lines.map((l, n) => (
              <Fragment key={n}>
                {n > 0 && <br />}
                <Inline text={l} />
              </Fragment>
            ))}
          </p>
        ) : b.kind === "ul" ? (
          <ul key={i} className="flex list-disc flex-col gap-1 pl-5">
            {b.items.map((it, n) => (
              <li key={n}><Inline text={it} /></li>
            ))}
          </ul>
        ) : (
          <ol key={i} className="flex list-decimal flex-col gap-1 pl-5">
            {b.items.map((it, n) => (
              <li key={n}><Inline text={it} /></li>
            ))}
          </ol>
        ),
      )}
    </div>
  );
}
