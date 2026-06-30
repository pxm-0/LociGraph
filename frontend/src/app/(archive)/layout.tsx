import { AppShell } from "@/components/app-shell";
import { ProtectedView } from "@/components/protected-view";

export default function ArchiveLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedView>
      <AppShell>{children}</AppShell>
    </ProtectedView>
  );
}
