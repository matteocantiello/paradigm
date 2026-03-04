import { useState } from "react";
import { Image, X } from "lucide-react";
import { paperFigureUrl } from "@/api/client";
import { EmptyState } from "@/components/shared/EmptyState";

interface FiguresTabProps {
  paperId: string;
  files: string[];
}

export function FiguresTab({ paperId, files }: FiguresTabProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (files.length === 0) {
    return (
      <EmptyState
        icon={Image}
        title="No figures"
        description="No figures were generated for this paper."
      />
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {files.map((file) => {
          const url = paperFigureUrl(paperId, file);
          return (
            <button
              key={file}
              onClick={() => setExpanded(file)}
              className="group rounded-md border border-border overflow-hidden hover:border-indigo-500/40 transition-colors"
            >
              <div className="aspect-square bg-muted/30 flex items-center justify-center">
                <img
                  src={url}
                  alt={file}
                  className="max-w-full max-h-full object-contain"
                  loading="lazy"
                />
              </div>
              <div className="px-2 py-1.5 border-t border-border">
                <p className="text-xs text-muted-foreground truncate group-hover:text-foreground transition-colors">
                  {file}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Expanded modal */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setExpanded(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-background rounded-lg border border-border shadow-xl p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setExpanded(null)}
              className="absolute top-2 right-2 p-1 rounded hover:bg-muted transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <img
              src={paperFigureUrl(paperId, expanded)}
              alt={expanded}
              className="max-w-full max-h-[80vh] object-contain"
            />
            <p className="text-xs text-muted-foreground text-center mt-2">{expanded}</p>
          </div>
        </div>
      )}
    </>
  );
}
