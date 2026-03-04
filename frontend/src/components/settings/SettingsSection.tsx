import { forwardRef } from "react";
import { Save, RotateCcw, Loader2, type LucideIcon } from "lucide-react";

interface SettingsSectionProps {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  dirty: boolean;
  saving: boolean;
  error?: string | null;
  onSave: () => void;
  onReset: () => void;
  children: React.ReactNode;
}

export const SettingsSection = forwardRef<HTMLDivElement, SettingsSectionProps>(
  function SettingsSection(
    { id, icon: Icon, title, description, dirty, saving, error, onSave, onReset, children },
    ref,
  ) {
    return (
      <div id={id} ref={ref} className="rounded-lg border border-border bg-card">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted">
            <Icon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <h3 className="text-sm font-semibold">{title}</h3>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
        </div>

        {/* Body */}
        <div className="divide-y divide-border px-5">{children}</div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <div>
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onReset}
              disabled={!dirty}
              className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-40"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset
            </button>
            <button
              onClick={onSave}
              disabled={!dirty || saving}
              className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save
            </button>
          </div>
        </div>
      </div>
    );
  },
);
