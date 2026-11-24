import { mediaUrl } from "@/lib/api";
import type { ComponentOf, Image } from "@/lib/catalog-schema";

/** One picture from our media library, with the credit an open licence asks for. */
export function Photo({ image, className = "", sizes = "100vw", credit = true }: {
  image: Image;
  className?: string;
  sizes?: string;
  credit?: boolean;
}) {
  return (
    <figure className="flex min-w-0 flex-col gap-1">
      {/* eslint-disable-next-line @next/next/no-img-element -- files from our own media route, already sized and cached */}
      <img
        src={mediaUrl(image.src)}
        alt={image.alt}
        sizes={sizes}
        loading="lazy"
        decoding="async"
        className={`w-full rounded-md bg-line object-cover ${className}`}
      />
      {credit && image.credit && <Credit image={image} />}
    </figure>
  );
}

export function Credit({ image }: { image: Image }) {
  return (
    <figcaption className="truncate text-[11px] leading-tight text-muted" title={`${image.alt}. Photo: ${image.credit}`}>
      Photo: {image.source ? (
        <a href={image.source} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted hover:text-ink">
          {image.credit}
        </a>
      ) : (
        image.credit
      )}
      {image.licence ? `, ${image.licence}` : ""}
    </figcaption>
  );
}

/** One credit line for several pictures: "Photos: A, CC BY 4.0 · B, CC0". */
export function Credits({ images }: { images: Image[] }) {
  const credited = images.filter((i) => i.credit);
  if (!credited.length) return null;
  return (
    <p className="text-[11px] leading-snug text-muted">
      {credited.length > 1 ? "Photos: " : "Photo: "}
      {credited.map((i, n) => (
        <span key={i.src}>
          {n > 0 && " · "}
          {i.source ? (
            <a href={i.source} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted hover:text-ink">
              {i.credit}
            </a>
          ) : (
            i.credit
          )}
          {i.licence ? `, ${i.licence}` : ""}
        </span>
      ))}
    </p>
  );
}

/** Where each picture sits in the mosaic: the first is the hero, and the last fills its row. */
function tile(i: number, n: number) {
  const last = i === n - 1;
  if (n <= 2) return "col-span-2 row-span-2 sm:col-span-1";
  if (i === 0) return "col-span-2 row-span-2";
  // phones: two per row under the hero, so an odd one out takes the whole row
  const phone = (n - 1) % 2 === 1 && last ? "col-span-2" : "";
  // wider (three columns): the hero with two beside it, then rows of three
  const extra = (n - 3) % 3;
  const wide = i >= 3 && last && extra === 1 ? "sm:col-span-3" : i >= 3 && last && extra === 2 ? "sm:col-span-2" : "sm:col-span-1";
  return `${phone} ${wide}`;
}

/** Pictures of the places a planned or requested trip visits: a photo mosaic with one credit line. */
export function PhotoGallery({ title, images }: ComponentOf<"photo_gallery">) {
  const n = images.length;
  return (
    <section aria-label={title} className="w-full">
      <h3 className="mb-2 flex items-center gap-2 text-brand-sm font-semibold">
        <span aria-hidden className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-orange/10 text-brand-orange">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="1.75" y="2.75" width="12.5" height="10.5" rx="1.75" />
            <circle cx="5.5" cy="6.25" r="1.25" />
            <path d="m14.25 10.5-3.5-3.5-7 6.25" />
          </svg>
        </span>
        {title}
      </h3>
      <ul className={`grid auto-rows-[92px] grid-cols-2 gap-1.5 overflow-hidden rounded-card sm:auto-rows-[118px] ${n > 2 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {images.map((img, i) => (
          <li key={img.src} className={`group/tile relative overflow-hidden bg-line ${tile(i, n)}`}>
            {/* eslint-disable-next-line @next/next/no-img-element -- files from our own media route, already sized and cached */}
            <img
              src={mediaUrl(img.src)}
              alt={img.alt}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover transition-transform group-hover/tile:scale-[1.04]"
            />
            <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-brand-black/60 to-transparent px-2 pb-1.5 pt-6 text-[11px] font-medium leading-tight text-brand-white opacity-0 transition-opacity group-hover/tile:opacity-100">
              {img.alt}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5">
        <Credits images={images} />
      </div>
    </section>
  );
}
