import { useEffect, useRef, useState } from "react";
import { DATASET_EXTS, formatSize, mergeDatasetFiles, previewDatasetColumns } from "@/lib/datasets";
import { Paperclip, Table2, X } from "lucide-react";

interface DatasetPickerProps {
  files: File[];
  onChange: (files: File[]) => void;
  /** Compact chips (hero console); default is the full list rows (wizard). */
  compact?: boolean;
  disabled?: boolean;
}

/**
 * Attach-dataset button + attached-file chips with a client-side schema peek
 * (CSV/TSV header columns), shared by the hero console and the SetupWizard.
 */
export function DatasetPicker({ files, onChange, compact = false, disabled = false }: DatasetPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [columns, setColumns] = useState<Record<string, string[]>>({});

  // Best-effort schema peek for tabular files; keyed by name+size.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next: Record<string, string[]> = {};
      for (const f of files) {
        const key = `${f.name}-${f.size}`;
        const cols = columns[key] ?? (await previewDatasetColumns(f));
        if (cols) next[key] = cols;
      }
      if (!cancelled) setColumns(next);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  const handlePick = (list: FileList | null) => {
    const { files: merged, error: problem } = mergeDatasetFiles(files, list);
    setError(problem);
    onChange(merged);
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={DATASET_EXTS.join(",")}
        className="hidden"
        onChange={(e) => {
          handlePick(e.target.files);
          e.target.value = "";
        }}
      />
      <div className={compact ? "flex flex-wrap items-center gap-1.5" : ""}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-40 transition-all"
        >
          <Paperclip className="h-3.5 w-3.5" />
          {files.length > 0 ? "Add another dataset" : "Attach data (optional)"}
        </button>
        {compact &&
          files.map((f) => (
            <span
              key={`${f.name}-${f.size}`}
              className="flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/40 px-2.5 py-1 text-[11px] font-mono"
              title={columnsTitle(columns[`${f.name}-${f.size}`])}
            >
              <Table2 className="h-3 w-3 text-accent-cyan" />
              <span className="max-w-[10rem] truncate">{f.name}</span>
              <span className="text-muted-foreground">{formatSize(f.size)}</span>
              <button
                type="button"
                onClick={() => onChange(files.filter((x) => x !== f))}
                className="text-muted-foreground hover:text-red-400 transition-colors"
                aria-label={`Remove ${f.name}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
      </div>
      {!compact && files.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {files.map((f) => {
            const cols = columns[`${f.name}-${f.size}`];
            return (
              <li
                key={`${f.name}-${f.size}`}
                className="rounded-md border border-border/50 bg-muted/30 px-3 py-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono truncate">
                    {f.name}{" "}
                    <span className="text-muted-foreground">({formatSize(f.size)})</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => onChange(files.filter((x) => x !== f))}
                    className="ml-2 text-muted-foreground hover:text-red-400 transition-colors"
                    aria-label={`Remove ${f.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                {cols && (
                  <p className="mt-1 flex items-start gap-1.5 text-[11px] text-muted-foreground">
                    <Table2 className="mt-0.5 h-3 w-3 shrink-0 text-accent-cyan" />
                    <span className="font-mono">
                      {cols.length} column{cols.length === 1 ? "" : "s"}:{" "}
                      {cols.slice(0, 8).join(", ")}
                      {cols.length > 8 ? ", …" : ""}
                    </span>
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && <p className="mt-1.5 text-xs text-red-400">{error}</p>}
    </div>
  );
}

function columnsTitle(cols: string[] | undefined): string {
  if (!cols) return "";
  return `${cols.length} columns: ${cols.join(", ")}`;
}
