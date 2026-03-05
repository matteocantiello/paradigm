import { Moon, Sun, Menu } from "lucide-react";
import { useUiStore } from "@/stores/uiStore";
import { useQuery } from "@tanstack/react-query";
import { healthCheck } from "@/api/client";
import { cn } from "@/lib/utils";
import { useConfigMode, useSetConfigMode } from "@/hooks/useConfigMode";

export function Header() {
  const { theme, toggleTheme, toggleSidebar, sidebarOpen } = useUiStore();

  const health = useQuery({
    queryKey: ["health"],
    queryFn: healthCheck,
    refetchInterval: 30_000,
    retry: 1,
  });

  const configMode = useConfigMode();
  const setMode = useSetConfigMode();

  const isHealthy = health.data?.status === "ok";
  const mode = configMode.data?.mode ?? "demo"; // "demo" | "testing" | "production"
  const testingAvailable = configMode.data?.testing_available ?? false;

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background/80 backdrop-blur-sm px-4 relative">
      {/* Subtle bottom glow line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent" />

      <div className="flex items-center gap-3">
        {!sidebarOpen && (
          <>
            <button onClick={toggleSidebar} className="text-muted-foreground hover:text-foreground transition-colors">
              <Menu className="h-4 w-4" />
            </button>
            <span className="text-xs font-semibold tracking-[0.12em] uppercase text-muted-foreground">
              Paradigm
            </span>
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="relative">
            <div
              className={cn(
                "h-2 w-2 rounded-full",
                health.isLoading
                  ? "bg-yellow-500"
                  : isHealthy
                    ? "bg-emerald-500"
                    : "bg-red-500"
              )}
            />
            {(health.isLoading || isHealthy) && (
              <div
                className={cn(
                  "absolute inset-0 rounded-full animate-ping",
                  health.isLoading ? "bg-yellow-500/50" : "bg-emerald-500/50"
                )}
                style={{ animationDuration: "2s" }}
              />
            )}
          </div>
          <span>{isHealthy ? "API Online" : "API Offline"}</span>
        </div>
        {testingAvailable ? (
          <button
            onClick={() => setMode.mutate(mode === "testing" ? "production" : "testing")}
            disabled={setMode.isPending}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-all",
              setMode.isPending && "opacity-50 cursor-not-allowed",
              mode === "testing"
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/25"
                : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/25"
            )}
          >
            <div className="relative">
              <div
                className={cn(
                  "h-2 w-2 rounded-full",
                  mode === "testing" ? "bg-amber-500" : "bg-emerald-500"
                )}
              />
            </div>
            {mode === "testing" ? "Testing" : "Production"}
          </button>
        ) : (
          <span className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium bg-amber-500/15 text-amber-600 dark:text-amber-400">
            <div className="h-2 w-2 rounded-full bg-amber-500" />
            Demo
          </span>
        )}
        <button
          onClick={toggleTheme}
          className="rounded-full p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-all"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>
    </header>
  );
}
