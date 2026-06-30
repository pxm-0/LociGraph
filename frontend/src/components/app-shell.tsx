"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Archive, Database, FileUp, LayoutDashboard, LogOut } from "lucide-react";

import { api } from "@/lib/api";
import { ModeProvider, useMode } from "@/components/mode-provider";
import { Orb } from "@/components/orb";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/import", label: "Import", icon: FileUp },
  { href: "/sources", label: "Sources", icon: Archive },
  { href: "/observations", label: "Observations", icon: Database }
];

function ShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { mode, setMode } = useMode();
  const hearth = mode === "hearth";

  async function logout() {
    await api.logout();
    router.push("/login");
  }

  return (
    <main
      className={
        hearth
          ? "min-h-screen bg-hearth text-[#172322] transition-colors duration-200"
          : "min-h-screen bg-archive text-dust transition-colors duration-200"
      }
    >
      <aside
        className={
          hearth
            ? "fixed left-0 top-0 z-10 hidden h-screen w-64 border-r border-teal/10 bg-white/40 px-5 py-6 backdrop-blur lg:block"
            : "fixed left-0 top-0 z-10 hidden h-screen w-64 border-r border-dust/[0.07] bg-void/35 px-4 py-5 backdrop-blur lg:block"
        }
      >
        <div className="font-display text-2xl font-semibold">LociGraph</div>
        <nav className={hearth ? "mt-10 space-y-2" : "mt-8 space-y-1"}>
          {navItems.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                  active
                    ? hearth
                      ? "bg-teal/10 text-teal"
                      : "bg-ember/10 text-ember"
                    : hearth
                      ? "text-[#46615f] hover:bg-teal/10"
                      : "text-ash hover:bg-dust/[0.04]"
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <header
        className={
          hearth
            ? "sticky top-0 z-10 border-b border-teal/10 bg-hearth/90 px-5 py-3 backdrop-blur lg:ml-64"
            : "sticky top-0 z-10 border-b border-dust/[0.07] bg-archive/90 px-5 py-3 backdrop-blur lg:ml-64"
        }
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex gap-1 lg:hidden">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  aria-label={item.label}
                  key={item.href}
                  href={item.href}
                  className="rounded-md p-2 text-current opacity-75"
                >
                  <Icon className="h-4 w-4" />
                </Link>
              );
            })}
          </div>
          <div className="hidden font-mono text-xs uppercase text-ash lg:block">
            Archive Interface
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border border-current/10 p-1">
              <button
                className={`rounded px-3 py-1 text-xs ${hearth ? "bg-teal text-white" : ""}`}
                onClick={() => setMode("hearth")}
                type="button"
              >
                Hearth
              </button>
              <button
                className={`rounded px-3 py-1 text-xs ${!hearth ? "bg-ember text-archive" : ""}`}
                onClick={() => setMode("meridian")}
                type="button"
              >
                Meridian
              </button>
            </div>
            <button
              aria-label="Log out"
              className="focus-ring rounded-md border border-current/10 p-2"
              onClick={logout}
              type="button"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <section className="px-5 py-8 lg:ml-64 lg:px-10">{children}</section>
      <Orb mode={mode} />
    </main>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ModeProvider>
      <ShellInner>{children}</ShellInner>
    </ModeProvider>
  );
}
