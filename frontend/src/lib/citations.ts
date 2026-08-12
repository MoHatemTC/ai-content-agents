import type { ChatCitation } from "@/types/domain";

/**
 * Turn the chunk ids an agent writes into its prose into readable links.
 *
 * `src/prompts/concept.yaml` and `mentor.yaml` instruct the model to reference
 * passages "by including the segment_id of each passage exactly as it appears",
 * so a reply arrives with `[8d3adb2f-63dc-4175-86f3-dfdf6b2fc6be-c0299]`
 * mid-sentence — a machine key shown to a learner. `describe_chunk_id` in
 * `src/retrieval/models.py` exists for exactly this and turns it into
 * "Passage 300"; it was only ever wired into the Streamlit UI and the
 * exporters, never into this one.
 *
 * The transform is display-only. What is stored keeps the exact ids, so
 * provenance stays auditable and old messages render better with no migration.
 */

/** A document uuid followed by the chunk's zero-padded ordinal. */
const CHUNK_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-c\d{3,}/gi;

/** A bracketed group of them — the model often lists several in one bracket. */
const CITATION_GROUP = /\[[^\]]*-c\d{3,}[^\]]*\]/g;

/** Marks a link produced here, so the renderer can style it as a chip. */
export const CITE_HREF_PREFIX = "#ref-";

/**
 * The label for one cited chunk.
 *
 * A page beats an ordinal for a learner holding the book, and the backend has
 * one (`document_chunks.page`). Without it, fall back to the ordinal using
 * `describe_chunk_id`'s 1-based convention — "Passage 0" reads as a bug to the
 * person being shown it.
 */
export function citationLabel(chunkId: string, citations: ChatCitation[]): string {
  const match = citations.find((c) => c.chunk === chunkId);
  if (match?.page) return `p. ${match.page}`;

  const ordinal = /-c(\d{3,})$/.exec(chunkId);
  if (ordinal) return `Passage ${Number(ordinal[1]) + 1}`;
  return chunkId;
}

/**
 * Rewrite inline chunk ids as markdown links.
 *
 * Emitting plain markdown means react-markdown parses them as ordinary link
 * nodes, so no custom remark plugin is needed and the surrounding maths and
 * formatting are untouched.
 *
 * Ids the message does not carry a citation for are still linked, and the
 * renderer marks them unverified — the same call `src/ui_common.py` makes when
 * a cited id is not in the retrieved set. Dropping them silently would hide
 * that the model cited something it was not given.
 */
export function linkifyCitations(text: string, citations: ChatCitation[]): string {
  if (!text) return text;

  return text.replace(CITATION_GROUP, (group) => {
    const ids = group.match(CHUNK_ID);
    if (!ids || ids.length === 0) return group;

    return ids
      .map((id) => `[${citationLabel(id, citations)}](${CITE_HREF_PREFIX}${id})`)
      .join(" ");
  });
}
