import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { FileText, HelpCircle, Layers, History as HistoryIcon, Lightbulb } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { SearchService } from "@/services";
import { useServiceQuery } from "@/hooks/useServiceQuery";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { SearchResult, SearchResultKind } from "@/types/domain";

const kindIcon: Record<SearchResultKind, React.ComponentType<{ className?: string }>> = {
  document: FileText,
  question: HelpCircle,
  flashcard: Layers,
  concept: Lightbulb,
  history: HistoryIcon,
};

const groupLabel: Record<SearchResultKind, string> = {
  document: "Documents",
  question: "Questions",
  flashcard: "Flashcards",
  concept: "Concepts",
  history: "History",
};

const ORDER: SearchResultKind[] = ["document", "question", "flashcard", "concept", "history"];

export function GlobalSearch({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const navigate = useNavigate();
  const { active } = useWorkspace();
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebounced(term), 200);
    return () => clearTimeout(id);
  }, [term]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  // Search is scoped to the active workspace; without one there is nothing to search.
  const workspaceId = active ? active.id : "";
  const { data, isPending, isError, error } = useServiceQuery(
    ["search", workspaceId, debounced],
    () => SearchService.search({ q: debounced, workspaceId }),
    { enabled: open && active != null, staleTime: 30_000 },
  );

  const go = (to: string) => {
    onOpenChange(false);
    navigate({ to });
  };

  const results = data?.results ?? [];
  const grouped = ORDER.map((kind) => ({
    kind,
    items: results.filter((r: SearchResult) => r.kind === kind),
  })).filter((g) => g.items.length > 0);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        value={term}
        onValueChange={setTerm}
        placeholder="Search documents, questions, flashcards, history…"
      />
      <CommandList>
        {isPending && (
          <div className="text-muted-foreground py-6 text-center text-sm">Searching…</div>
        )}
        {isError && (
          <div role="alert" className="text-destructive py-6 text-center text-sm">
            {error?.message ?? "Search is unavailable right now."}
          </div>
        )}
        {!isPending && !isError && <CommandEmpty>No results found.</CommandEmpty>}
        {!isPending &&
          !isError &&
          grouped.map((group) => {
            const Icon = kindIcon[group.kind];
            return (
              <CommandGroup key={group.kind} heading={groupLabel[group.kind]}>
                {group.items.map((r) => (
                  <CommandItem
                    key={`${r.kind}-${r.id}`}
                    value={`${r.title} ${r.subtitle ?? ""}`}
                    onSelect={() => go(r.to)}
                  >
                    <Icon className="size-4" />
                    <span className="truncate">{r.title}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            );
          })}
      </CommandList>
    </CommandDialog>
  );
}
