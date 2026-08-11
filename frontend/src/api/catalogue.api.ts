/** Catalogue endpoints: agents, pipeline stages, notifications, demo catalogue. */
import { delay, http, HttpError } from "./http";
import { paths } from "./paths";
import { isMockMode } from "@/config/env";
import {
  agents as seedAgents,
  documents as seedDocuments,
  flashcards as seedFlashcards,
  history as seedHistory,
  pipelineSteps as seedPipeline,
} from "@/mock/mock-data";
import { notifications as seedNotifications, ragStages as seedRagStages } from "@/mock/studio-data";
import type {
  CatalogueResponse,
  GetAgentResponse,
  ListAgentsResponse,
  ListNotificationsQuery,
  ListNotificationsResponse,
  ListPipelineStepsResponse,
  ListRagStagesResponse,
} from "@/types/api/catalogue.contracts";

/** GET /agents */
export async function getAgents(): Promise<ListAgentsResponse> {
  if (!isMockMode()) return http.get<ListAgentsResponse>(paths.catalogue.agents);
  await delay(320);
  return { agents: seedAgents };
}

/** GET /agents/{slug} */
export async function getAgent(slug: string): Promise<GetAgentResponse> {
  if (!isMockMode()) return http.get<GetAgentResponse>(paths.catalogue.agent(slug));
  await delay(200);
  const agent = seedAgents.find((a) => a.slug === slug);
  if (!agent) throw new Error(`Agent "${slug}" does not exist.`);
  return { agent };
}

/** GET /pipeline/steps */
export async function getPipelineSteps(workspaceId?: string): Promise<ListPipelineStepsResponse> {
  if (!isMockMode()) {
    const url = `${paths.catalogue.pipelineSteps}${workspaceId ? `?workspace_id=${workspaceId}` : ""}`;
    try {
      return await http.get<ListPipelineStepsResponse>(url);
    } catch (err) {
      // The backend does not serve /pipeline/steps yet (Phase 8 gap), so a 404
      // would dead-end the whole page. Fall back to the seeded nine-stage view
      // so the RAG pipeline page keeps rendering.
      if (err instanceof HttpError && err.status === 404) {
        await delay(120);
        return { steps: seedPipeline, completed: 7 };
      }
      throw err;
    }
  }
  await delay(260);
  return { steps: seedPipeline, completed: 7 };
}

/** GET /pipeline/stages */
export async function getRagStages(): Promise<ListRagStagesResponse> {
  if (!isMockMode()) return http.get<ListRagStagesResponse>(paths.catalogue.pipelineStages);
  await delay(240);
  return { stages: seedRagStages };
}

/** GET /notifications */
export async function getNotifications(
  query: ListNotificationsQuery = {},
): Promise<ListNotificationsResponse> {
  if (!isMockMode()) {
    return http.get<ListNotificationsResponse>(
      `${paths.catalogue.notifications}${query.role ? `?role=${query.role}` : ""}`,
    );
  }
  await delay(300);
  const notifications = query.role
    ? seedNotifications.filter((n) => n.roles.includes(query.role!))
    : seedNotifications;
  return { notifications, unread: notifications.filter((n) => n.unread).length };
}

/** PATCH /notifications/{id}/read */
export async function markNotificationRead(id: string): Promise<{ id: string }> {
  if (!isMockMode()) return http.patch<{ id: string }>(paths.catalogue.notificationRead(id));
  await delay(80);
  return { id };
}

/** POST /notifications/read-all */
export async function markAllNotificationsRead(): Promise<{ updated: number }> {
  if (!isMockMode()) return http.post<{ updated: number }>(paths.catalogue.notificationsReadAll);
  await delay(120);
  return { updated: seedNotifications.filter((n) => n.unread).length };
}

/** GET /catalogue — demo documents, history and flashcards used by dashboards. */
export async function getCatalogue(): Promise<CatalogueResponse> {
  if (!isMockMode()) return http.get<CatalogueResponse>(paths.catalogue.catalogue);
  await delay(380);
  return { documents: seedDocuments, history: seedHistory, flashcards: seedFlashcards };
}
