import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Code2, FileCode } from "lucide-react";
import { getPaperExperiment } from "@/api/client";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";
import { cn } from "@/lib/utils";

interface CodeTabProps {
  paperId: string;
  files: string[];
}

export function CodeTab({ paperId, files }: CodeTabProps) {
  const [selectedFile, setSelectedFile] = useState<string>(files[0] ?? "");

  const { data: content, isLoading } = useQuery({
    queryKey: ["paper-experiment", paperId, selectedFile],
    queryFn: () => getPaperExperiment(paperId, selectedFile),
    enabled: !!selectedFile,
  });

  if (files.length === 0) {
    return (
      <EmptyState
        icon={Code2}
        title="No experiment code"
        description="No experiment files were generated for this paper."
      />
    );
  }

  return (
    <div className="flex gap-4">
      {/* File list */}
      <div className="w-48 shrink-0 border-r border-border pr-3">
        <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Files
        </h3>
        <div className="space-y-0.5">
          {files.map((file) => (
            <button
              key={file}
              onClick={() => setSelectedFile(file)}
              className={cn(
                "w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-xs text-left transition-colors",
                selectedFile === file
                  ? "bg-indigo-500/15 text-indigo-300"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              )}
            >
              <FileCode className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{file}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Code viewer */}
      <div className="flex-1 min-w-0">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : content?.content ? (
          <pre className="rounded-md border border-border bg-muted/30 p-4 text-xs leading-relaxed overflow-x-auto font-mono whitespace-pre">
            {content.content}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground">Select a file to view its contents.</p>
        )}
      </div>
    </div>
  );
}
