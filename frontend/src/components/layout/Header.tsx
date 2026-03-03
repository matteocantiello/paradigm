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
  const isTesting = configMode.data?.mode === "testing";
  const testingAvailable = configMode.data?.testing_available ?? false;

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-background px-4">
      <div className="flex items-center gap-3">
        {!sidebarOpen && (
          <button onClick={toggleSidebar} className="text-muted-foreground hover:text-foreground">
            <Menu className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div
            className={cn(
              "h-2 w-2 rounded-full",
              health.isLoading
                ? "bg-yellow-500 animate-pulse"
                : isHealthy
                  ? "bg-green-500"
                  : "bg-red-500"
            )}
          />
          <span>{isHealthy ? "API Online" : "API Offline"}</span>
        </div>
        {testingAvailable && (
          <button
            onClick={() => setMode.mutate(isTesting ? "production" : "testing")}
            disabled={setMode.isPending}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors",
              setMode.isPending && "opacity-50 cursor-not-allowed",
              isTesting
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/25"
                : "bg-green-500/15 text-green-600 dark:text-green-400 hover:bg-green-500/25"
            )}
          >
            <div
              className={cn(
                "h-2 w-2 rounded-full",
                isTesting ? "bg-amber-500" : "bg-green-500"
              )}
            />
            {isTesting ? "Testing" : "Production"}
          </button>
        )}
        <button
          onClick={toggleTheme}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>
    </header>
  );
}
