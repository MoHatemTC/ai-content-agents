import { motion } from "motion/react";
import { Github, Linkedin, Sparkles } from "lucide-react";
import sprintsLogo from "@/assets/sprints-logo.png";

export interface TeamMember {
  name: string;
  role: string;
  focus: string;
  contribution: string;
  initials: string;
  linkedin: string;
  github: string;
}

export const TEAM: TeamMember[] = [
  {
    name: "Nour Atef",
    role: "AI Platform & Validation Engineer",
    focus: "Retrieval pipeline",
    contribution:
      "Developed the retrieval and grounding pipeline, validation, human-review, orchestration, and evaluation systems. Also performed end-to-end testing to ensure AI outputs were accurate, grounded, validated, and properly reviewed.",
    initials: "NA",
    linkedin: "https://www.linkedin.com/in/nour-atef-450ba7274",
    github: "https://github.com/NourAtef112",
  },
  {
    name: "Yousef Alaa",
    role: "AI Engineer & Frontend Developer",
    focus: "Multi-agent system",
    contribution:
      "Developed the Mentor, Concept Explanation, Question Bank, and Test Help agents with grounded generation, structured outputs, and human-review integration. Also contributed to the product frontend.",
    initials: "YA",
    linkedin: "https://www.linkedin.com/in/yousef-alaa-azab/",
    github: "https://github.com/joo156",
  },
  {
    name: "Fardia Yousry",
    role: "Content Pipeline & Quality Assurance Engineer",
    focus: "Product interface",
    contribution:
      "Developed and tested the content ingestion and library workflow, including content processing, quality checks, metadata, and demo data. Also performed end-to-end testing of the complete AI pipeline and reported integration issues.",
    initials: "FY",
    linkedin: "https://linkedin.com",
    github: "https://github.com/Farida-Yousry",
  },
  {
    name: "Ahmed Mousa",
    role: "AI & Content Processing Engineer",
    focus: "APIs & storage",
    contribution:
      "Built the content ingestion pipeline for parsing, cleaning, chunking, storing, and de-duplicating documents. Also developed the Flashcard, Study Plan, and Revision agents with grounded generation and structured outputs.",
    initials: "AM",
    linkedin: "https://linkedin.com",
    github: "https://github.com/ahmed25102004",
  },
  {
    name: "Reem Mahmoud & Mohamed Hatem",
    role: "Technical Leads & Project Mentors",
    focus: "Technical guidance",
    contribution:
      "Guided the team by planning sprints, assigning tasks, supporting technical decisions, resolving blockers, and coordinating development across project workstreams.",
    initials: "RM & MH",
    linkedin: "https://linkedin.com",
    github: "https://github.com",
  },
];

export function TeamSection({ id = "team" }: { id?: string }) {
  return (
    <section id={id} className="py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="max-w-2xl"
        >
          <p className="text-primary mb-2 text-sm font-semibold">Meet the team</p>
          <h2 className="text-3xl font-bold tracking-tight">
            Four students, one grounded learning platform
          </h2>
          <p className="text-muted-foreground mt-3 leading-relaxed">
            Every part of this product — retrieval, agents, interface and evaluation — was designed
            and built by the team below.
          </p>
        </motion.div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TEAM.map((m, i) => {
            const isMentor = m.role === "Technical Leads & Project Mentors";

            return (
              <motion.article
                key={m.name}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ delay: i * 0.07, duration: 0.45, ease: "easeOut" }}
                whileHover={{ y: -6 }}
                className="surface-card hover:border-primary/40 hover:shadow-elevated group relative overflow-hidden p-6 transition-all"
              >
                {isMentor ? (
                  <>
                    {/* Special mentor glow */}
                    <span className="bg-primary/10 pointer-events-none absolute -top-16 -right-16 size-40 rounded-full blur-2xl" />
                    <span className="bg-primary/5 pointer-events-none absolute -bottom-16 -left-16 size-32 rounded-full blur-2xl" />

                    <div className="relative">
                      {/* Mentor badge */}
                      <div className="mb-5 flex items-center gap-2">
                        <span className="bg-primary/10 text-primary inline-flex size-9 items-center justify-center rounded-xl">
                          <Sparkles className="size-4" />
                        </span>

                        <div className="min-w-0">
                          <p className="text-primary text-[10px] font-bold uppercase tracking-widest">
                            Technical Mentors
                          </p>
                          <p className="text-muted-foreground text-xs">Project Leadership</p>
                        </div>
                      </div>

                      {/* Mentor names */}
                      <h3 className="text-sm font-semibold leading-snug">{m.name}</h3>

                      <p className="text-primary mt-1 text-xs font-medium">{m.role}</p>

                      <p className="text-muted-foreground mt-4 text-sm leading-relaxed">
                        {m.contribution}
                      </p>

                      <div className="text-muted-foreground mt-4 flex items-center text-xs">
                        <span className="border-primary/20 bg-primary/5 text-primary rounded-full border px-2 py-0.5">
                          {m.focus}
                        </span>
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <span className="bg-primary/8 pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100" />

                    <div className="flex items-center gap-3">
                      <motion.span
                        whileHover={{ rotate: -6, scale: 1.06 }}
                        className="bg-primary text-primary-foreground shadow-glow flex size-12 items-center justify-center rounded-2xl text-sm font-bold"
                      >
                        {m.initials}
                      </motion.span>

                      <div className="min-w-0">
                        <h3 className="truncate text-sm font-semibold">{m.name}</h3>
                        <p className="text-primary truncate text-xs font-medium">{m.role}</p>
                      </div>
                    </div>

                    <p className="text-muted-foreground mt-4 text-sm leading-relaxed">
                      {m.contribution}
                    </p>

                    <div className="text-muted-foreground mt-4 flex items-center gap-3 text-xs">
                      <span className="border-border rounded-full border px-2 py-0.5">
                        {m.focus}
                      </span>

                      <span className="ml-auto flex items-center gap-1.5">
                        <a
                          href={m.linkedin}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`${m.name} on LinkedIn`}
                          className="border-border text-muted-foreground hover:border-primary/50 hover:text-primary hover:bg-primary/10 inline-flex size-7 items-center justify-center rounded-lg border transition-all hover:-translate-y-0.5"
                        >
                          <Linkedin className="size-3.5" />
                        </a>

                        <a
                          href={m.github}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`${m.name} on GitHub`}
                          className="border-border text-muted-foreground hover:border-primary/50 hover:text-primary hover:bg-primary/10 inline-flex size-7 items-center justify-center rounded-lg border transition-all hover:-translate-y-0.5"
                        >
                          <Github className="size-3.5" />
                        </a>
                      </span>
                    </div>
                  </>
                )}
              </motion.article>
            );
          })}

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ delay: 0.35, duration: 0.45 }}
            className="surface-card flex flex-col justify-center gap-4 p-6"
          >
            <span className="self-start rounded-xl bg-white px-3 py-2 ring-1 ring-black/5">
              <img
                src={sprintsLogo}
                alt="Sprints AI logo"
                className="h-9 w-auto object-contain"
                loading="lazy"
              />
            </span>

            <p className="text-sm leading-relaxed">
              This platform was designed and engineered end to end by our team during the{" "}
              <strong>Sprints AI</strong> training programme — a hands-on apprenticeship where
              students ship a real, production-shaped AI product rather than a course exercise.
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
