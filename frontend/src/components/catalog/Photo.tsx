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

/** Pictures of the places a planned or requested trip visits. */
export function PhotoGallery({ title, images }: ComponentOf<"photo_gallery">) {
  return (
    <section aria-label={title} className="w-full">
      <h3 className="mb-2 text-brand-sm font-semibold">{title}</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {images.map((img) => (
          <Photo key={img.src} image={img} sizes="(min-width: 640px) 33vw, 50vw" className="aspect-[4/3]" />
        ))}
      </div>
    </section>
  );
}
