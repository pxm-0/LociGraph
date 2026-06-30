"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";

import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to enter archive");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-archive px-5 text-dust">
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-[10px] border border-dust/[0.07] bg-chamber p-8"
      >
        <div className="mb-8">
          <h1 className="font-display text-4xl font-semibold">LociGraph</h1>
          <p className="mt-3 text-sm leading-6 text-ash">
            Private access to the archive.
          </p>
        </div>
        <label className="block text-sm text-ash" htmlFor="password">
          Password
        </label>
        <div className="mt-2 flex items-center gap-2 rounded-md border border-dust/[0.08] bg-archive px-3">
          <LockKeyhole className="h-4 w-4 text-ash" />
          <input
            id="password"
            className="focus-ring h-12 min-w-0 flex-1 bg-transparent text-sm text-dust placeholder:text-ash"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter archive password"
            type="password"
            value={password}
          />
        </div>
        {error ? <p className="mt-3 text-sm text-[#E5A2A2]">{error}</p> : null}
        <button
          className="focus-ring mt-6 h-11 w-full rounded-md bg-ember px-4 text-sm font-medium text-archive disabled:bg-[#B88340] disabled:text-void"
          disabled={busy || !password}
          type="submit"
        >
          {busy ? "Entering" : "Enter Archive"}
        </button>
      </form>
    </main>
  );
}
