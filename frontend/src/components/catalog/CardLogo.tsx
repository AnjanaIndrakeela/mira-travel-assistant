import type { Brand } from "@/lib/card";

// Small card-network marks for the mock checkout, drawn inline (no image files, nothing fetched).
// They keep the networks' own colours, so they are outside the brand palette on purpose.

const NAMES: Record<Brand, string> = { visa: "Visa", mastercard: "Mastercard", amex: "American Express" };

/** A card-shaped logo, 40 x 26 by default. Decorative unless `title` is given. */
export function CardLogo({ brand, className = "h-[26px] w-10", title = false }: {
  brand: Brand;
  className?: string;
  title?: boolean;
}) {
  const label = title ? { role: "img", "aria-label": NAMES[brand] } : { "aria-hidden": true };
  return (
    <svg viewBox="0 0 40 26" className={`shrink-0 ${className}`} {...label}>
      {brand === "visa" && (
        <>
          <rect x="0.5" y="0.5" width="39" height="25" rx="4" fill="#fff" stroke="#E6E6E6" />
          <text x="20" y="17.5" textAnchor="middle" fontFamily="Arial, Helvetica, sans-serif" fontSize="12.5"
            fontWeight="900" fontStyle="italic" letterSpacing="-0.3" fill="#1A1F71">VISA</text>
          <path d="M8 20.5h24" stroke="#F7B600" strokeWidth="1.4" strokeLinecap="round" />
        </>
      )}
      {brand === "mastercard" && (
        <>
          <rect x="0.5" y="0.5" width="39" height="25" rx="4" fill="#fff" stroke="#E6E6E6" />
          <circle cx="15.5" cy="13" r="7.5" fill="#EB001B" />
          <circle cx="24.5" cy="13" r="7.5" fill="#F79E1B" />
          <path d="M20 7a7.5 7.5 0 0 1 0 12 7.5 7.5 0 0 1 0-12z" fill="#FF5F00" />
        </>
      )}
      {brand === "amex" && (
        <>
          <rect width="40" height="26" rx="4" fill="#016FD0" />
          <text x="20" y="16.6" textAnchor="middle" fontFamily="Arial, Helvetica, sans-serif" fontSize="9.5"
            fontWeight="900" letterSpacing="0.4" fill="#fff">AMEX</text>
        </>
      )}
    </svg>
  );
}
