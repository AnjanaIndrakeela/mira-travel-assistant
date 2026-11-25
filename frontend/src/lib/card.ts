// Mock card checks in the browser: the same rules the server applies again in
// backend/app/booking/mock_payment.py (the server's answer is the one that counts).
// Nothing here stores or sends the card anywhere but POST /bookings.

export const BRANDS = [
  { id: "visa", name: "Visa", short: "Visa", cvc: 3, groups: [4, 4, 4, 4, 3] },
  { id: "mastercard", name: "Mastercard", short: "Mastercard", cvc: 3, groups: [4, 4, 4, 4] },
  { id: "amex", name: "American Express", short: "Amex", cvc: 4, groups: [4, 6, 5] },
] as const;
export type Brand = (typeof BRANDS)[number]["id"];
export type CardField = "holder" | "brand" | "number" | "expiry" | "cvc";

export const brandInfo = (b: Brand) => BRANDS.find((x) => x.id === b)!;

/** Demo cards anyone can use (published test numbers; never real cards). */
export const TEST_CARDS: { label: string; brand: Brand; number: string; cvc: string }[] = [
  { label: "Visa •••• 4242", brand: "visa", number: "4242 4242 4242 4242", cvc: "123" },
  { label: "Visa •••• 0002", brand: "visa", number: "4000 0000 0000 0002", cvc: "123" },
  { label: "Mastercard •••• 4444", brand: "mastercard", number: "5555 5555 5555 4444", cvc: "123" },
  { label: "Amex •••• 0005", brand: "amex", number: "3782 822463 10005", cvc: "1234" },
];

export const digitsOf = (s: string) => s.replace(/\D/g, "");

export function luhnOk(digits: string): boolean {
  let total = 0;
  for (let i = 0; i < digits.length; i++) {
    let n = Number(digits[digits.length - 1 - i]) * (i % 2 ? 2 : 1);
    if (n > 9) n -= 9;
    total += n;
  }
  return total % 10 === 0;
}

/** The card type a (possibly partial) number points to, from its first digits. */
export function guessBrand(digits: string): Brand | null {
  if (/^4/.test(digits)) return "visa";
  if (/^(5[1-5]|222[1-9]|22[3-9]|2[3-6]|27[01]|2720)/.test(digits)) return "mastercard";
  if (/^3[47]/.test(digits)) return "amex";
  return null;
}

/** "4242424242424242" -> "4242 4242 4242 4242"; Amex as 4-6-5. */
export function formatNumber(raw: string, brand: Brand | null): string {
  const d = digitsOf(raw).slice(0, brand === "amex" ? 15 : 19);
  const groups: readonly number[] = brand ? brandInfo(brand).groups : [4, 4, 4, 4, 3];
  const out: string[] = [];
  let i = 0;
  for (const g of groups) {
    if (i >= d.length) break;
    out.push(d.slice(i, i + g));
    i += g;
  }
  return out.join(" ");
}

/** "1228" / "12/28" -> "12/28" while typing. */
export function formatExpiry(raw: string, prev: string): string {
  let d = digitsOf(raw).slice(0, 4);
  if (d.length === 1 && Number(d) > 1) d = `0${d}`; // "4" -> "04"
  if (raw.length < prev.length && prev.endsWith("/") && d.length === 2) return d.slice(0, 1); // backspace over "/"
  return d.length >= 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
}

export type CardInput = { holder: string; brand: Brand; number: string; expiry: string; cvc: string };

/** Problems by field (empty = looks fine). `today` is the browser's date; the server uses its own. */
export function checkCard(c: CardInput, today = new Date()): Partial<Record<CardField, string>> {
  const errors: Partial<Record<CardField, string>> = {};
  const info = brandInfo(c.brand);
  const digits = digitsOf(c.number);
  if (!/\p{L}/u.test(c.holder) || c.holder.trim().length < 2) errors.holder = "Enter the name as it's written on the card.";
  if (digits.length < 12 || !luhnOk(digits)) errors.number = "This card number doesn't look right.";
  else if (guessBrand(digits) !== c.brand || (c.brand === "amex" && digits.length !== 15))
    errors.brand = `That number isn't a ${info.name} card.`;
  const m = /^(\d{2})\/(\d{2})$/.exec(c.expiry);
  if (!m || Number(m[1]) < 1 || Number(m[1]) > 12) errors.expiry = "Use MM/YY, for example 08/29.";
  else {
    const end = new Date(2000 + Number(m[2]), Number(m[1]), 0, 23, 59, 59); // last day of that month
    if (end < today) errors.expiry = "This card has expired.";
  }
  if (!new RegExp(`^\\d{${info.cvc}}$`).test(c.cvc))
    errors.cvc = `${info.cvc} digits, on the ${c.brand === "amex" ? "front" : "back"} of the card.`;
  return errors;
}

/** What POST /bookings expects. */
export function toPayload(c: CardInput) {
  const [mm, yy] = c.expiry.split("/");
  return { holder: c.holder.trim(), brand: c.brand, number: digitsOf(c.number), exp_month: Number(mm), exp_year: Number(yy), cvc: c.cvc };
}
