import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useUiStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";

export function AppShell() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <div
        className={cn(
          "hidden md:block transition-all duration-300 ease-in-out",
          sidebarOpen ? "w-56" : "w-0 overflow-hidden"
        )}
      >
        <Sidebar />
      </div>
      <div className="flex flex-1 flex-col overflow-hidden relative">
        {/* Subtle radial glow from top-left */}
        <div className="absolute inset-0 pointer-events-none dark:bg-[radial-gradient(ellipse_at_top_left,_oklch(0.75_0.15_190_/_0.03)_0%,_transparent_50%)]" />
        <Header />
        <main className="flex-1 overflow-auto p-4 relative">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
