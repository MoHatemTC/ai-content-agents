import senseiMark from "@/assets/sensei-mark.png";
import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <img
      src={senseiMark}
      alt="Sensei logo"
      className={cn(
        "size-9 shrink-0 object-contain transition-all dark:brightness-0 dark:invert",
        className,
      )}
    />
  );
}
