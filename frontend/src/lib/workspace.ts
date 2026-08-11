/** Pure workspace helpers shared by the UI, services and mock seeds. */
import type { WorkspaceData } from "@/types/domain";

/** A brand-new, empty workspace payload. */
export function emptyWorkspaceData(): WorkspaceData {
  return {
    docs: [],
    questions: [],
    flashcards: [],
    chats: [],
    history: [],
    weakTopics: [],
    audit: [],
  };
}
