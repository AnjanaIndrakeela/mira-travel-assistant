"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Card, Field, Pill } from "@/components/catalog/ui";
import { safeNext } from "@/components/staff/StaffShell";
import { ApiError } from "@/lib/api";
import { staffApi } from "@/lib/staff-api";

function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await staffApi.login(email.trim(), password);
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-8 flex max-w-sm justify-center">
      <Card accent="teal" wide label="Staff sign-in">
        <h1 className="text-brand-lg font-bold">Staff sign-in</h1>
        <p className="text-brand-sm text-muted">For Ceylon Compass Holidays staff only.</p>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                 required maxLength={254} autoComplete="username" autoFocus />
          <Field label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 required maxLength={200} autoComplete="current-password" />
          {error && <p role="alert" className="text-brand-sm text-accent-coral">{error}</p>}
          <Pill type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Pill>
        </form>
      </Card>
    </div>
  );
}

export default function StaffLogin() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
