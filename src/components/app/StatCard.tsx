import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  delta,
  icon: Icon,
  index = 0,
  className,
}: {
  label: string;
  value: string;
  delta?: string;
  icon: LucideIcon;
  index?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.35, ease: "easeOut" }}
      whileHover={{ y: -3 }}
      className={cn("surface-card hover:shadow-elevated p-5 transition-shadow", className)}
    >
      <div className="flex items-start justify-between">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{label}</p>
        <span className="bg-primary/10 text-primary flex size-8 items-center justify-center rounded-lg">
          <Icon className="size-4" />
        </span>
      </div>
      <p className="mt-4 text-3xl font-semibold tracking-tight">{value}</p>
      {delta && <p className="text-muted-foreground mt-1 text-xs">{delta}</p>}
    </motion.div>
  );
}
