import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  AlertTriangle,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Heart,
  RotateCw,
  Shuffle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { Citation } from "@/types/domain";

export interface Flashcard {
  id: string;
  front: string;
  back: string;
  topic?: string;
  format?: string;
  citations?: Citation[];
}

export function FlashcardDeck({
  cards: initial,
  favorites,
  onToggleFavorite,
}: {
  cards: Flashcard[];
  /** Front-text keys the user has favorited (persisted via FavoriteService). */
  favorites?: Set<string>;
  /** When provided, toggling delegates persistence to the caller. */
  onToggleFavorite?: (card: Flashcard) => void;
}) {
  const [cards, setCards] = useState(initial);
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [favs, setFavs] = useState<Set<string>>(favorites ?? new Set());
  const [hard, setHard] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<"study" | "quiz">("study");

  useEffect(() => setFavs(favorites ?? new Set()), [favorites]);

  useEffect(() => setFlipped(false), [i, mode]);

  const current = cards[i];
  const progress = useMemo(() => ((i + 1) / cards.length) * 100, [i, cards.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") prev();
      if (e.key === " ") {
        e.preventDefault();
        setFlipped((f) => !f);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i, cards.length]);

  const next = () => setI((n) => (n + 1) % cards.length);
  const prev = () => setI((n) => (n - 1 + cards.length) % cards.length);

  const shuffle = () => {
    const arr = [...cards];
    for (let k = arr.length - 1; k > 0; k--) {
      const j = Math.floor(Math.random() * (k + 1));
      [arr[k], arr[j]] = [arr[j], arr[k]];
    }
    setCards(arr);
    setI(0);
    toast.success("Deck shuffled");
  };

  const toggleFav = () => {
    if (onToggleFavorite) {
      onToggleFavorite(current);
      return;
    }
    setFavs((s) => {
      const n = new Set(s);
      if (n.has(current.front)) n.delete(current.front);
      else n.add(current.front);
      return n;
    });
  };
  const toggleHard = () => {
    setHard((s) => {
      const n = new Set(s);
      if (n.has(current.id)) n.delete(current.id);
      else n.add(current.id);
      return n;
    });
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="border-border bg-muted/40 inline-flex rounded-lg border p-0.5">
          {(["study", "quiz"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors",
                mode === m ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
              )}
            >
              {m} mode
            </button>
          ))}
        </div>
        <span className="text-muted-foreground text-xs">
          {i + 1} / {cards.length}
        </span>
        <div className="bg-muted ml-2 h-1.5 flex-1 overflow-hidden rounded-full">
          <motion.div className="bg-primary h-full" animate={{ width: `${progress}%` }} />
        </div>
        <Button variant="ghost" size="sm" onClick={shuffle}>
          <Shuffle className="size-3.5" /> Shuffle
        </Button>
      </div>
      <div className="[perspective:1600px]">
        <motion.button
          type="button"
          onClick={() => setFlipped((f) => !f)}
          className="relative block h-72 w-full [transform-style:preserve-3d] focus:outline-none"
          animate={{ rotateY: flipped ? 180 : 0 }}
          transition={{ duration: 0.55, ease: "easeInOut" }}
        >
          <div className="surface-card absolute inset-0 flex flex-col items-center justify-center gap-4 p-8 text-center [backface-visibility:hidden]">
            <span className="text-muted-foreground text-[11px] font-semibold tracking-widest uppercase">
              {mode === "quiz" ? "Question" : "Front"}
              {current.topic ? ` · ${current.topic}` : ""}
            </span>
            <p className="text-2xl leading-tight font-semibold">{current.front}</p>
            <span className="text-muted-foreground mt-auto text-xs">
              Click or press Space to flip
            </span>
          </div>
          <div className="surface-card absolute inset-0 flex flex-col gap-4 overflow-y-auto p-8 text-center [backface-visibility:hidden] [transform:rotateY(180deg)]">
            <span className="text-primary text-[11px] font-semibold tracking-widest uppercase">
              {mode === "quiz" ? "Answer" : "Back"}
              {current.format ? ` · ${current.format}` : ""}
            </span>
            <p className="text-xl leading-relaxed">{current.back}</p>
            {current.citations && current.citations.length > 0 && (
              <CardReferences citations={current.citations} />
            )}
          </div>
        </motion.button>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        <Button variant="outline" size="sm" onClick={prev}>
          <ChevronLeft className="size-4" /> Prev
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setFlipped((f) => !f)}>
          <RotateCw className="size-3.5" /> Flip
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleHard}
          className={cn(hard.has(current.id) && "text-warning")}
        >
          <AlertTriangle className="size-3.5" /> Mark difficult
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleFav}
          className={cn(favs.has(current.front) && "text-destructive")}
        >
          <Heart className={cn("size-3.5", favs.has(current.front) && "fill-current")} /> Favorite
        </Button>
        <Button variant="outline" size="sm" onClick={next}>
          Next <ChevronRight className="size-4" />
        </Button>
      </div>
      <p className="text-muted-foreground mt-3 text-center text-[11px]">
        {hard.size} marked difficult · {favs.size} favorited · Spaced repetition prioritises
        difficult cards next session
      </p>{" "}
    </div>
  );
}

function CardReferences({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-auto w-full border-t pt-3 text-left">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "border-border text-muted-foreground inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors hover:border-primary/40 hover:text-primary",
          open && "border-primary/40 text-primary",
        )}
      >
        <BookOpen className="size-3.5" />
        {open ? "Hide sources" : `Show sources (${citations.length})`}
      </button>
      {open && (
        <div className="border-border mt-2 max-h-40 space-y-2 overflow-y-auto border-l-2 pl-3">
          {citations.map((c, i) => (
            <div key={`${c.chunk ?? c.doc}-${i}`} className="text-xs leading-relaxed">
              <p className="text-primary font-semibold">
                Source · {c.chunk ?? c.doc.slice(0, 8)}
                {c.page ? ` · p.${c.page}` : ""}
              </p>
              <p className="text-muted-foreground line-clamp-3">{c.snippet}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
