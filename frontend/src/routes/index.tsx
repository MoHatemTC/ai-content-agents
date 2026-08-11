import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import {
  ArrowRight,
  BookOpen,
  Brain,
  ClipboardList,
  FileCode2,
  FileText,
  FileType,
  GraduationCap,
  Layers,
  Lightbulb,
  MessagesSquare,
  ShieldCheck,
  Sparkles,
  Upload,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/app/theme";
import { BrandMark } from "@/components/app/BrandMark";
import { TeamSection } from "@/components/app/TeamSection";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Sensei — Transform Content Into Intelligent Learning Assets" },
      {
        name: "description",
        content:
          "Upload any lecture material and generate grounded question banks, flashcards, study plans, and mentor conversations — with citations you can trust.",
      },
      { property: "og:title", content: "Sensei — Grounded AI Study Workspace" },
      {
        property: "og:description",
        content: "Upload → Understand → Generate → Review → Export. Every answer cites a source.",
      },
    ],
  }),
  component: Landing,
});

const FEATURES = [
  {
    icon: ClipboardList,
    name: "Question Bank",
    blurb: "MCQ, short answer, true/false — every option grounded.",
  },
  {
    icon: MessagesSquare,
    name: "Mentor",
    blurb: "Conversational tutor that only speaks from your material.",
  },
  {
    icon: GraduationCap,
    name: "Test Help",
    blurb: "Timed exam simulations with instant feedback.",
  },
  { icon: Layers, name: "Flashcards", blurb: "Animated cards, shuffle, spaced repetition." },
  {
    icon: Lightbulb,
    name: "Concept Explanation",
    blurb: "Ask about any idea — get a cited breakdown.",
  },
  {
    icon: BookOpen,
    name: "Study Plan",
    blurb: "Timeline, calendar and checklist tailored to your deadline.",
  },
  {
    icon: Brain,
    name: "Revision Assistant",
    blurb: "Weak-topic detection and revision checklists.",
  },
];

const STEPS = [
  { icon: Upload, title: "Upload", body: "PDFs, decks, notes — up to 200 MB per file." },
  {
    icon: Wand2,
    title: "AI understands",
    body: "Parsing, chunking and embedding with hybrid retrieval.",
  },
  {
    icon: Sparkles,
    title: "Generate",
    body: "Pick an agent, tune controls, generate grounded assets.",
  },
  {
    icon: ShieldCheck,
    title: "Review",
    body: "Human-in-the-loop approval before anything leaves the workspace.",
  },
  {
    icon: FileText,
    title: "Export",
    body: "PDF, Markdown, JSON or CSV — cite-ready for classrooms.",
  },
];

const FILE_TYPES = [
  { icon: FileText, label: "PDF" },
  { icon: FileType, label: "DOCX" },
  { icon: FileCode2, label: "Markdown" },
  { icon: FileText, label: "TXT" },
];

function Landing() {
  return (
    <div className="bg-background text-foreground min-h-screen">
      <header className="border-border/50 sticky top-0 z-20 border-b backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <BrandMark className="size-9" />
            <span className="text-[15px] font-semibold tracking-tight">Sensei</span>
          </Link>
          <nav className="ml-6 hidden gap-6 text-sm md:flex">
            <a href="#features" className="text-muted-foreground hover:text-foreground">
              Features
            </a>
            <a href="#how" className="text-muted-foreground hover:text-foreground">
              How it works
            </a>
            <a href="#files" className="text-muted-foreground hover:text-foreground">
              File types
            </a>
            <a href="#team" className="text-muted-foreground hover:text-foreground">
              Team
            </a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <Button asChild variant="ghost" size="sm">
              <Link to="/login">Sign in</Link>
            </Button>
            <Button asChild size="sm" className="cta-shine group">
              <Link to="/login">
                Start learning
                <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mesh-bg relative overflow-hidden">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:py-28">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <span className="border-border bg-card/70 text-muted-foreground inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs">
              <ShieldCheck className="text-primary size-3.5" /> Grounded generation · Every claim
              cites a chunk
            </span>
            <h1 className="mt-5 text-4xl leading-[1.05] font-semibold tracking-tight sm:text-5xl lg:text-6xl">
              Transform educational content into{" "}
              <span className="text-primary">intelligent learning assets</span>.
            </h1>
            <p className="text-muted-foreground mt-5 max-w-xl text-lg">
              Upload any document. Generate question banks, study plans, flashcards, concept
              explanations and mentor conversations — all grounded, all cited, all reviewable.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg" className="cta-shine group px-7">
                <Link to="/login">
                  <Sparkles className="size-5 transition-transform duration-500 group-hover:rotate-180 group-hover:scale-110" />
                  Start learning
                  <ArrowRight className="size-4 opacity-0 -translate-x-2 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="cta-sweep group px-7">
                <a href="#how">
                  <span className="bg-primary/15 text-primary flex size-6 items-center justify-center rounded-full transition-transform duration-500 group-hover:scale-110">
                    <ArrowRight className="size-3.5 transition-transform duration-500 group-hover:translate-y-0.5 group-hover:rotate-90" />
                  </span>
                  See how it works
                </a>
              </Button>
            </div>
            <div className="text-muted-foreground mt-6 flex flex-wrap items-center gap-4 text-xs">
              <span>Demo accounts:</span>
              <code className="bg-muted rounded px-2 py-1">student@sensei.ai</code>
              <code className="bg-muted rounded px-2 py-1">reviewer@sensei.ai</code>
              <code className="bg-muted rounded px-2 py-1">admin@sensei.ai</code>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="relative"
          >
            <div className="surface-card shadow-elevated p-6">
              <div className="mb-4 flex items-center gap-2 text-xs">
                <span className="bg-primary/12 text-primary rounded-md px-2 py-1 font-semibold">
                  Question Bank
                </span>
                <span className="text-muted-foreground">Introduction to Python · Ch.3</span>
                <span className="text-success ml-auto inline-flex items-center gap-1">
                  <ShieldCheck className="size-3.5" /> 98% grounded
                </span>
              </div>
              <p className="text-base font-medium">
                Which type stores a single Unicode character in Python?
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {["int", "bool", "str", "double"].map((o, i) => (
                  <div
                    key={o}
                    className={`rounded-xl border px-3 py-2 text-sm ${
                      i === 2
                        ? "border-success bg-success/10 font-medium"
                        : "border-border bg-muted/40 text-muted-foreground"
                    }`}
                  >
                    {o}
                  </div>
                ))}
              </div>
              <p className="text-muted-foreground mt-3 text-xs">
                <span className="text-success font-semibold">Correct.</span> Python has no dedicated
                char type — single characters are just length-1 <code>str</code>.
              </p>
            </div>
            <div className="bg-primary/20 absolute -inset-4 -z-10 rounded-[2rem] blur-3xl" />
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Seven agents, one grounded workspace.
          </h2>
          <p className="text-muted-foreground mt-3">
            Each agent is purpose-built. Generators just generate. Tutors just tutor.
          </p>
        </div>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.name}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.04 }}
              className="surface-card hover:border-primary/40 p-5 transition-colors"
            >
              <span className="bg-primary/10 text-primary flex size-10 items-center justify-center rounded-xl">
                <f.icon className="size-5" />
              </span>
              <p className="mt-4 font-semibold">{f.name}</p>
              <p className="text-muted-foreground mt-1 text-sm">{f.blurb}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="bg-muted/30 border-border border-y">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">How it works</h2>
            <p className="text-muted-foreground mt-3">Five stages, fully transparent.</p>
          </div>
          <ol className="mt-12 grid gap-4 md:grid-cols-5">
            {STEPS.map((s, i) => (
              <li key={s.title} className="surface-card p-5">
                <span className="text-muted-foreground font-mono text-xs">Step {i + 1}</span>
                <s.icon className="text-primary mt-2 size-6" />
                <p className="mt-3 font-semibold">{s.title}</p>
                <p className="text-muted-foreground mt-1 text-sm">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* File types */}
      <section id="files" className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Bring any material.</h2>
          <p className="text-muted-foreground mt-3">
            Upload lectures, papers, decks, notes — Sensei parses, chunks and embeds them.
          </p>
        </div>
        <div className="mt-10 flex flex-wrap justify-center gap-3">
          {FILE_TYPES.map((f) => (
            <span
              key={f.label}
              className="surface-card flex items-center gap-2 px-4 py-2 text-sm font-medium"
            >
              <f.icon className="text-primary size-4" /> {f.label}
            </span>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-4xl px-4 pb-24 sm:px-6">
        <div className="surface-card mesh-bg p-10 text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Ready to study smarter?
          </h2>
          <p className="text-muted-foreground mx-auto mt-3 max-w-xl">
            Sign in with a demo account and generate your first grounded question bank in under a
            minute.
          </p>
          <Button asChild size="lg" className="mt-6">
            <Link to="/login">
              Start learning <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>
      </section>

      <TeamSection />

      <footer className="border-border border-t">
        <div className="text-muted-foreground mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-6 text-xs sm:px-6">
          <span>© Sensei · Grounded learning assets</span>
          <span className="ml-auto">
            Designed and built by a student team during the Sprints AI training programme.
          </span>
        </div>
      </footer>
    </div>
  );
}
