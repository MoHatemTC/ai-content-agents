import { Cpu } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { ModelService } from "@/services/ModelService";

/** Catalogue comes from the service layer — never hardcoded in the UI. */
export const MODELS = ModelService.list();

export type ModelId = string;

export function ModelSelector({
  value,
  onChange,
  className,
}: {
  value: ModelId;
  onChange: (v: ModelId) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as ModelId)}>
      <SelectTrigger className={className ?? "h-9 w-auto min-w-44 gap-2"}>
        <Cpu className="text-muted-foreground size-3.5" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {MODELS.map((m) => (
          <SelectItem key={m.id} value={m.id} disabled={!m.available}>
            <span className="flex items-center gap-2">
              <span className="font-medium">{m.name}</span>
              <span className="text-muted-foreground text-[11px]">{m.vendor}</span>
              {!m.available && (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                    "bg-warning/15 text-warning",
                  )}
                >
                  Soon
                </span>
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
