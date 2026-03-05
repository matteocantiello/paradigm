import { forwardRef } from "react";
import { RotateCcw, Loader2, type LucideIcon } from "lucide-react";

interface SettingsSectionProps {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  saving: boolean;
  error?: string | null;
  onReset: () => void;
  children: React.ReactNode;
}

export const SettingsSection = forwardRef<HTMLDivElement, SettingsSectionProps>(
  function SettingsSection(
    { id, icon: Icon, title, description, saving, error, onReset, children },
    ref,
  ) {
    return (
      <div id={id} ref={ref} className="rounded-lg border border-border bg-card">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
            <Icon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold">{title}</h3>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
          <div className="flex items-center gap-2">
            {saving && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            )}
            <button
              onClick={onReset}
              className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              title="Reset to defaults"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="divide-y divide-border px-5">{children}</div>

        {/* Error footer — only shown when there's an error */}
        {error && (
          <div className="border-t border-border px-5 py-3">
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}
      </div>
    );
  },
);
