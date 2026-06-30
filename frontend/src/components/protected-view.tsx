"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export function ProtectedView({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(() => setReady(true))
      .catch(() => router.replace("/login"));
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-archive p-8 text-dust">
        <div className="h-8 w-48 rounded bg-dust/10" />
        <div className="mt-8 h-32 max-w-3xl rounded-md bg-dust/[0.06]" />
      </div>
    );
  }

  return <>{children}</>;
}
