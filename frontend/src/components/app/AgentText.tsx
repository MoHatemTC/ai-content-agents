import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import { cn } from "@/lib/utils";

/**
 * The single place model prose becomes DOM.
 *
 * The agent prompts instruct the model to write mathematics as LaTeX -
 * `src/prompts/concept.yaml` even tells it "the interface renders it, so
 * notation belongs in notation". That was true of the Streamlit UI, which
 * rendered through `st.markdown`. It was not true here: every agent reply was
 * printed verbatim, so a linear-algebra explanation arrived as a wall of
 * `$\mathbb{R}^n$`. This closes that gap rather than weakening the prompt,
 * because the notation is worth having once something draws it.
 *
 * Raw HTML stays disabled (react-markdown's default). Model output is
 * untrusted text that can carry an uploaded document's content with it, so it
 * is never given a route to the DOM other than markdown.
 *
 * The `[?]` marker the prompts use for notation that did not survive
 * extraction is literal text and passes through untouched.
 */
export function AgentText({
  children,
  className,
}: {
  children: string | null | undefined;
  className?: string;
}) {
  if (!children) return null;

  return (
    <div className={cn("agent-prose", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Bind to the surrounding type scale instead of browser defaults:
          // this renders inside cards and chat bubbles that already set size.
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => (
            <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
          ),
          h1: ({ children }) => (
            <h1 className="mt-3 mb-1 text-base font-semibold first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h3>
          ),
          code: ({ children }) => (
            <code className="bg-muted/60 rounded px-1 py-0.5 font-mono text-[0.9em]">
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="bg-muted/60 mb-2 overflow-x-auto rounded-lg p-3 text-xs last:mb-0">
              {children}
            </pre>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="text-primary underline underline-offset-2"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="mb-2 overflow-x-auto last:mb-0">
              <table className="w-full text-left text-xs">{children}</table>
            </div>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-border text-muted-foreground mb-2 border-l-2 pl-3 last:mb-0">
              {children}
            </blockquote>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
