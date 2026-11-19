import type {
  DatasetDetail,
  DatasetSummary,
  Health,
  ReviewStatus,
  RowsPage,
  Suggestion,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Not JSON; keep the generic message.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  health: () => request<Health>("/health"),

  listDatasets: () => request<DatasetSummary[]>("/datasets"),

  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DatasetSummary>("/datasets", { method: "POST", body: form });
  },

  getDataset: (id: string) => request<DatasetDetail>(`/datasets/${id}`),

  deleteDataset: (id: string) => request<void>(`/datasets/${id}`, { method: "DELETE" }),

  getRows: (id: string, offset: number, limit: number) =>
    request<RowsPage>(`/datasets/${id}/rows?offset=${offset}&limit=${limit}`),

  getSuggestions: (id: string) => request<Suggestion[]>(`/datasets/${id}/suggestions`),

  review: (id: string, suggestionId: string, status: ReviewStatus, finalValue?: string) =>
    request<Suggestion>(
      `/datasets/${id}/suggestions/${suggestionId}`,
      json("PATCH", { status, final_value: finalValue ?? null }),
    ),

  bulkReview: (id: string, ids: string[], status: ReviewStatus) =>
    request<Suggestion[]>(`/datasets/${id}/suggestions/bulk`, json("POST", { ids, status })),

  exportUrl: (id: string) => `/api/datasets/${id}/export`,
  auditUrl: (id: string) => `/api/datasets/${id}/audit`,
};
