// Dataset attachment helpers shared by the landing hero console and the
// SetupWizard. Mirrors the backend allowlist in backend/api/routes/research.py.

export const DATASET_EXTS = [
  ".csv", ".tsv", ".txt", ".json", ".dat", ".fits", ".parquet", ".npy", ".npz", ".h5", ".hdf5",
];
export const DATASET_MAX_MB = 100;

export function formatSize(bytes: number): string {
  if (bytes > 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

/** Validate a candidate dataset file. Returns an error message, or null if OK. */
export function validateDatasetFile(f: File): string | null {
  const ext = f.name.includes(".") ? "." + f.name.split(".").pop()!.toLowerCase() : "";
  if (!DATASET_EXTS.includes(ext)) {
    return `Unsupported type "${ext || f.name}" — allowed: ${DATASET_EXTS.join(" ")}`;
  }
  if (f.size > DATASET_MAX_MB * 1024 * 1024) {
    return `${f.name} is too large (max ${DATASET_MAX_MB} MB)`;
  }
  return null;
}

/**
 * Merge newly picked files into an existing list (deduped by name+size).
 * Returns the merged list and the first validation error hit, if any.
 */
export function mergeDatasetFiles(
  current: File[],
  picked: FileList | File[] | null
): { files: File[]; error: string | null } {
  if (!picked) return { files: current, error: null };
  const next = [...current];
  let error: string | null = null;
  for (const f of Array.from(picked)) {
    const problem = validateDatasetFile(f);
    if (problem) {
      error = problem;
      continue;
    }
    if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f);
  }
  return { files: next, error };
}

/**
 * Client-side schema peek for tabular files: the header columns of a CSV/TSV.
 * Returns null for non-tabular types or unparseable content — callers just
 * skip the preview then.
 */
export async function previewDatasetColumns(f: File): Promise<string[] | null> {
  const ext = f.name.includes(".") ? "." + f.name.split(".").pop()!.toLowerCase() : "";
  if (![".csv", ".tsv"].includes(ext)) return null;
  try {
    const head = await f.slice(0, 4096).text();
    const line = head.split(/\r?\n/).find((l) => l.trim().length > 0);
    if (!line) return null;
    const delim = ext === ".tsv" || line.includes("\t") ? "\t" : ",";
    const cols = line
      .split(delim)
      .map((c) => c.trim().replace(/^["']|["']$/g, ""))
      .filter((c) => c.length > 0);
    return cols.length > 0 ? cols : null;
  } catch {
    return null;
  }
}
