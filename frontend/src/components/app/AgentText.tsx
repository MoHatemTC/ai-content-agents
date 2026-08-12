import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import { CITE_HREF_PREFIX, linkifyCitations } from "@/lib/citations";
import { cn } from "@/lib/utils";
import type { ChatCitation } from "@/types/domain";

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
  citations,
  inline,
}: {
  children: string | null | undefined;
  className?: string;
  /** Lets an inline chunk id be labelled with its page and linked to its entry. */
  citations?: ChatCitation[];
  /**
   * Render as phrasing content only - a `<span>` with no block-level output.
   *
   * Block elements (`<p>`, `<ul>`, ...) are invalid inside a `<button>`, which
   * is what an MCQ option or a True/False choice is. Everything else -
   * remark-math, rehype-katex, the citation-chip handler - is unchanged.
   */
  inline?: boolean;
}) {
  if (!children) return null;

  const text = linkifyCitations(children, citations ?? []);
  const Root = inline ? "span" : "div";
  const Block = inline ? "span" : "p";
  const List = inline ? "span" : "ul";
  const OrderedList = inline ? "span" : "ol";
  const Heading = inline ? "span" : undefined;

  return (
    <Root className={cn("agent-prose", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Bind to the surrounding type scale instead of browser defaults:
          // this renders inside cards and chat bubbles that already set size.
          p: ({ children }) => <Block className={inline ? undefined : "mb-2 last:mb-0"}>{children}</Block>,
          ul: ({ children }) => (
            <List className={inline ? undefined : "mb-2 list-disc space-y-1 pl-5 last:mb-0"}>
              {children}
            </List>
          ),
          ol: ({ children }) => (
            <OrderedList
              className={inline ? undefined : "mb-2 list-decimal space-y-1 pl-5 last:mb-0"}
            >
              {children}
            </OrderedList>
          ),
          li: ({ children }) => (inline ? <span>{children}</span> : <li>{children}</li>),
          h1: ({ children }) =>
            Heading ? (
              <Heading>{children}</Heading>
            ) : (
              <h1 className="mt-3 mb-1 text-base font-semibold first:mt-0">{children}</h1>
            ),
          h2: ({ children }) =>
            Heading ? (
              <Heading>{children}</Heading>
            ) : (
              <h2 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h2>
            ),
          h3: ({ children }) =>
            Heading ? (
              <Heading>{children}</Heading>
            ) : (
              <h3 className="mt-3 mb-1 text-sm font-semibold first:mt-0">{children}</h3>
            ),
          code: ({ children }) => (
            <code className="bg-muted/60 rounded px-1 py-0.5 font-mono text-[0.9em]">
              {children}
            </code>
          ),
          pre: ({ children }) =>
            inline ? (
              <span className="font-mono text-[0.9em]">{children}</span>
            ) : (
              <pre className="bg-muted/60 mb-2 overflow-x-auto rounded-lg p-3 text-xs last:mb-0">
                {children}
              </pre>
            ),
          a: ({ children, href }) => {
            // Citation markers are rewritten into links by linkifyCitations so
            // react-markdown parses them without a custom plugin; they are
            // rendered as chips rather than links.
            if (href?.startsWith(CITE_HREF_PREFIX)) {
              const chunk = href.slice(CITE_HREF_PREFIX.length);
              const known = (citations ?? []).some((c) => c.chunk === chunk);
              return (
                <a
                  href={href}
                  title={
                    known
                      ? undefined
                      : // Same call src/ui_common.py makes: say the model cited
                        // something outside the retrieved set rather than hide it.
                        `Unverified citation — the model cited ${chunk}, which is not among this reply's sources`
                  }
                  onClick={(event) => {
                    event.preventDefault();
                    window.dispatchEvent(
                      new CustomEvent("sensei:cite", { detail: { chunk } }),
                    );
                  }}
                  className={cn(
                    "mx-0.5 inline-flex items-baseline rounded border px-1 align-baseline text-[0.7em] font-medium no-underline transition-colors",
                    known
                      ? "border-primary/30 text-primary hover:bg-primary/10"
                      : "border-warning/40 text-warning hover:bg-warning/10",
                  )}
                >
                  {children}
                </a>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className="text-primary underline underline-offset-2"
              >
                {children}
              </a>
            );
          },
          table: ({ children }) =>
            inline ? (
              <span>{children}</span>
            ) : (
              <div className="mb-2 overflow-x-auto last:mb-0">
                <table className="w-full text-left text-xs">{children}</table>
              </div>
            ),
          blockquote: ({ children }) =>
            inline ? (
              <span>{children}</span>
            ) : (
              <blockquote className="border-border text-muted-foreground mb-2 border-l-2 pl-3 last:mb-0">
                {children}
              </blockquote>
            ),
        }}
      >
        {text}
      </ReactMarkdown>
    </Root>
  );
}
