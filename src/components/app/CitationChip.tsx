import { Quote } from "lucide-react";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Button } from "@/components/ui/button";
import type { SourceRef } from "@/types/domain";
import { toast } from "sonner";

export function CitationChip({ source, index }: { source: SourceRef; index?: number }) {
  return (
    <HoverCard openDelay={80} closeDelay={80}>
      <HoverCardTrigger asChild>
        <button className="border-primary/25 bg-primary/8 text-primary hover:bg-primary/15 inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 text-[11px] font-medium transition-colors">
          <Quote className="size-3" />
          {index != null ? `[${index + 1}] ` : ""}
          p.{source.page}
        </button>
      </HoverCardTrigger>
      <HoverCardContent className="w-80" align="start">
        <p className="text-xs font-semibold">{source.doc}</p>
        <p className="text-muted-foreground text-[11px]">
          page {source.page} · {source.chunk} · {(source.score * 100).toFixed(0)}% match
        </p>
        <p className="border-primary/25 text-muted-foreground mt-2 border-l-2 pl-2 font-mono text-[11px] leading-relaxed">
          {source.snippet}
        </p>
        <div className="mt-3 flex gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={() => toast.info("Highlighted source chunk")}
          >
            Highlight chunk
          </Button>
          <Button size="sm" variant="ghost" onClick={() => toast.info("Opening original document")}>
            Open document
          </Button>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
