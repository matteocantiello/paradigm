interface FieldRowProps {
  label: string;
  description?: string;
  children: React.ReactNode;
}

function FieldRow({ label, description, children }: FieldRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

// --- Toggle ---

interface ToggleFieldProps {
  label: string;
  description?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}

export function ToggleField({ label, description, value, onChange }: ToggleFieldProps) {
  return (
    <FieldRow label={label} description={description}>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
          value ? "bg-primary" : "bg-muted"
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-background shadow-sm ring-0 transition-transform ${
            value ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </button>
    </FieldRow>
  );
}

// --- Number ---

interface NumberFieldProps {
  label: string;
  description?: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}

export function NumberField({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step,
}: NumberFieldProps) {
  return (
    <FieldRow label={label} description={description}>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm text-right focus:outline-none focus:ring-1 focus:ring-ring"
      />
    </FieldRow>
  );
}

// --- Select ---

interface SelectFieldProps {
  label: string;
  description?: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}

export function SelectField({
  label,
  description,
  value,
  onChange,
  options,
}: SelectFieldProps) {
  return (
    <FieldRow label={label} description={description}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </FieldRow>
  );
}

// --- Text (for memory_limit etc.) ---

interface TextFieldProps {
  label: string;
  description?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

export function TextField({
  label,
  description,
  value,
  onChange,
  placeholder,
}: TextFieldProps) {
  return (
    <FieldRow label={label} description={description}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm text-right focus:outline-none focus:ring-1 focus:ring-ring"
      />
    </FieldRow>
  );
}
