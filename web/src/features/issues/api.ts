import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../shared/api/client";
import type { Issue, IssueAction, Watch } from "../../shared/api/types";

export const useIssues = () =>
  useQuery({
    queryKey: ["issues"],
    queryFn: () => api.get<{ issues: Issue[]; watch: Watch[] }>("/api/issues"),
  });

export interface ActionInput {
  action: IssueAction["action"];
  note: string;
  owner?: string;
  effective_at?: string;
}

export function useIssueAction(key: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ActionInput) => api.post<IssueAction>(`/api/issues/${key}/actions`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["issues"] });
      void qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}
