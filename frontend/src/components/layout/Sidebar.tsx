import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FlaskConical,
  FileText,
  Users,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/research", icon: FlaskConical, label: "Research" },
  { to: "/papers", icon: FileText, label: "Papers" },
  { to: "/agents", icon: Users, label: "Agents" },
];

export function Sidebar() {
  return (
    <aside className="flex h-full w-56 flex-col border-r border-sidebar-border bg-gradient-to-b from-sidebar to-[oklch(0.09_0.02_260)] dark:to-[oklch(0.09_0.02_260)]">
      <div className="flex items-center gap-3 px-4 py-4 border-b border-sidebar-border">
        {/* Observatory logo mark — aperture rings + a small orbiting star */}
        <div className="relative h-8 w-8 flex items-center justify-center shrink-0">
          <div className="absolute inset-0 rounded-full border-2 border-primary/60 glow-sm" />
          <div className="absolute inset-1.5 rounded-full border border-primary/40" />
          <div className="h-2 w-2 rounded-full bg-primary" />
          <div className="absolute h-1 w-1 rounded-full bg-accent-cyan top-0 right-0.5 animate-breathe" />
        </div>
        <div className="flex flex-col leading-none">
          <span className="font-display text-[19px] font-semibold tracking-tight text-sidebar-foreground">
            Paradigm
          </span>
          <span className="text-[9px] font-mono uppercase tracking-[0.28em] text-muted-foreground/60 mt-1">
            Observatory
          </span>
        </div>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-all relative",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-primary glow-sm"
                  : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground border-l-2 border-transparent"
              )
            }
          >
            {({ isActive }) => (
              <>
                <div className={cn(
                  "flex items-center justify-center h-6 w-6 rounded-full transition-colors",
                  isActive ? "bg-primary/15" : ""
                )}>
                  <Icon className="h-4 w-4" />
                </div>
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="px-2 pb-2">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-all border-l-2",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground border-primary glow-sm"
                : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground border-transparent"
            )
          }
        >
          {({ isActive }) => (
            <>
              <div className={cn(
                "flex items-center justify-center h-6 w-6 rounded-full transition-colors",
                isActive ? "bg-primary/15" : ""
              )}>
                <Settings className="h-4 w-4" />
              </div>
              Settings
            </>
          )}
        </NavLink>
      </div>
      <div className="px-4 pb-3">
        <span className="text-[10px] text-muted-foreground/40 font-mono">v0.1 alpha</span>
      </div>
    </aside>
  );
}
