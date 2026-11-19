import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { ReviewStatus, Suggestion } from "./types";

const POLL_MS = 1000;

export const keys = {
  health: ["health"] as const,
  datasets: ["datasets"] as const,
  dataset: (id: string) => ["dataset", id] as const,
  suggestions: (id: string) => ["suggestions", id] as const,
  rows: (id: string, offset: number) => ["rows", id, offset] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, staleTime: 60_000 });
}

export function useDataset(id: string) {
  return useQuery({
    queryKey: keys.dataset(id),
    queryFn: () => api.getDataset(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : POLL_MS;
    },
  });
}

export function useSuggestions(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.suggestions(id),
    queryFn: () => api.getSuggestions(id),
    enabled,
  });
}

interface ReviewInput {
  ids: string[];
  status: ReviewStatus;
  finalValue?: string;
}

/**
 * Updates the cached list immediately and rolls back if the request fails, so
 * accepting a group of 200 suggestions feels instant.
 */
export function useReview(datasetId: string) {
  const client = useQueryClient();
  const key = keys.suggestions(datasetId);

  return useMutation({
    mutationFn: async ({ ids, status, finalValue }: ReviewInput): Promise<Suggestion[]> => {
      const [first] = ids;
      if (ids.length === 1 && first) {
        return [await api.review(datasetId, first, status, finalValue)];
      }
      return api.bulkReview(datasetId, ids, status);
    },
    onMutate: async ({ ids, status, finalValue }) => {
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<Suggestion[]>(key);
      const changed = new Set(ids);
      client.setQueryData<Suggestion[]>(key, (current) =>
        current?.map((s) =>
          changed.has(s.id)
            ? {
                ...s,
                status,
                final_value: status === "pending" ? null : (finalValue ?? s.final_value),
              }
            : s,
        ),
      );
      return { previous };
    },
    onError: (_error, _input, context) => {
      if (context?.previous) client.setQueryData(key, context.previous);
    },
    onSettled: () => client.invalidateQueries({ queryKey: key }),
  });
}
