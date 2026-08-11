/** Mentor + concept chat business logic. */
import * as chatApi from "@/api/chat.api";
import { getProvider, type ChatContext } from "./ai/AIProvider";
import { attempt } from "@/lib/result";
import type { Result } from "@/types/api/common";
import type { CreateChatRequest, CreateChatResponse } from "@/types/api/chat.contracts";
import type { WsChatMessage } from "@/types/domain";
import type { ChatKind } from "@/types/database.types";

export const ChatService = {
  createChat(req: CreateChatRequest): Promise<Result<CreateChatResponse>> {
    return attempt("ChatService.createChat", () => chatApi.createChat(req));
  },

  async listChats(workspaceId: string) {
    return attempt("ChatService.listChats", () => chatApi.getChats(workspaceId));
  },

  async send(input: {
    kind: ChatKind;
    workspaceId: string;
    chatId: string;
    message: string;
    model: string;
    documentIds?: string[];
    context: ChatContext;
  }): Promise<Result<WsChatMessage>> {
    return attempt("ChatService.send", async () => {
      const provider = getProvider(input.model);
      const req = {
        workspaceId: input.workspaceId,
        chatId: input.chatId,
        message: input.message,
        model: input.model,
        documentIds: input.documentIds,
      };
      const res =
        input.kind === "mentor"
          ? await provider.mentorChat(req, input.context)
          : await provider.conceptChat(req, input.context);
      return { ...res.message, citations: res.citations };
    });
  },
};
