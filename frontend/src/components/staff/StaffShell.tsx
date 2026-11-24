"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { brand } from "@/lib/brand";
import { type Me, staffApi } from "@/lib/staff-api";

type Ctx = { me: Me; signedOut: (err: unknown) => boolean };
const StaffContext = createContext<Ctx | null>(null);

export function useStaff(): Ctx {
  const ctx = useContext(StaffContext);
  if (!ctx) throw new Error("useStaff outside StaffShell");
  return ctx;
}

/** Only staff pages may be the target after sign-in (no open redirect). */
export function safeNext(next: string | null): string {
  return next && /^\/staff\/[\w\-/]*$/.test(next) ? next : "/staff/enquiries";
}

/** Staff pages: checks the session first, and sends anyone signed out to the sign-in page. */
export function StaffShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const isLogin = pathname === "/staff/login";
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toLogin = useCallback(() => {
    router.replace(`/staff/login?next=${encodeURIComponent(pathname)}`);
  }, [router, pathname]);

  const signedOut = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) {
        setMe(null);
        toLogin();
        return true;
      }
      return false;
    },
    [toLogin],
  );

  useEffect(() => {
    if (isLogin) return;
    let live = true;
    staffApi
      .me()
      .then((m) => live && setMe(m))
      .catch((err) => {
        if (!live) return;
        if (err instanceof ApiError && err.status === 401) toLogin();
        else setError(err instanceof ApiError ? err.message : "Something went wrong.");
      });
    return () => {
      live = false;
    };
  }, [isLogin, toLogin]);

  async function signOut() {
    try {
      await staffApi.logout();
    } finally {
      setMe(null);
      router.replace("/staff/login");
    }
  }

  return (
    <div className="min-h-dvh bg-[#F7F7F5]">
      <header className="sticky top-0 z-10 border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-3 px-4">
          <Link href="/staff/enquiries" className="flex min-w-0 items-center gap-2">
            <span aria-hidden className="h-6 w-6 shrink-0 rounded-full bg-brand-orange" />
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-brand-sm font-bold">{brand.name}</span>
              <span className="block text-brand-xs text-muted">Staff console</span>
            </span>
          </Link>
          {me && (
            <nav aria-label="Staff sections" className="flex items-center gap-1">
              {[
                ["/staff/enquiries", "Enquiries"],
                ["/staff/content", "Content"],
              ].map(([href, label]) => (
                <Link
                  key={href}
                  href={href}
                  aria-current={pathname.startsWith(href) ? "page" : undefined}
                  className={`rounded-button px-2.5 py-1.5 text-brand-xs font-semibold ${
                    pathname.startsWith(href) ? "bg-ink text-brand-white" : "hover:bg-line"
                  }`}
                >
                  {label}
                </Link>
              ))}
            </nav>
          )}
          {me && (
            <div className="flex items-center gap-3">
              <span className="hidden text-brand-xs text-muted sm:inline">
                {me.email} · {me.role}
              </span>
              <button
                type="button"
                onClick={signOut}
                className="rounded-button border border-line px-3 py-1.5 text-brand-xs font-semibold hover:border-ink focus-visible:outline-2 focus-visible:outline-brand-orange"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        {isLogin ? (
          children
        ) : error ? (
          <p role="alert" className="text-brand-sm text-accent-coral">{error}</p>
        ) : me ? (
          <StaffContext.Provider value={{ me, signedOut }}>{children}</StaffContext.Provider>
        ) : (
          <p className="text-brand-sm text-muted">Checking your sign-in…</p>
        )}
      </main>
    </div>
  );
}
