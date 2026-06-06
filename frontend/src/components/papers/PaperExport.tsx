import { Copy, Download, Check, FileDown } from "lucide-react";
import { useState } from "react";

interface PaperExportProps {
  title: string;
  body: string;
  pdfUrl?: string;
}

export function PaperExport({ title, body, pdfUrl }: PaperExportProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([body], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^\w\s-]/g, "").replace(/\s+/g, "-").toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={handleCopy}
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
        {copied ? "Copied" : "Copy Markdown"}
      </button>
      <button
        onClick={handleDownload}
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        <Download className="h-3.5 w-3.5" />
        Download .md
      </button>
      {pdfUrl && (
        <a
          href={pdfUrl}
          target="_blank"
          rel="noopener noreferrer"
          title="Download the typeset PDF (compiled on the server)"
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <FileDown className="h-3.5 w-3.5" />
          Download PDF
        </a>
      )}
    </div>
  );
}
