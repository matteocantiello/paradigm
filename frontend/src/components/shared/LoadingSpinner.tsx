import { cn } from "@/lib/utils";

export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <div className={cn("observatory-spinner", className)}>
      <div className="absolute inset-[10px] rounded-full bg-primary/20" />
    </div>
  );
}
