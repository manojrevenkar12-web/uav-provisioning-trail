import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api/client";
import type { Release, WhereUsed } from "../../shared/api/types";

export const useReleases = () =>
  useQuery({ queryKey: ["releases"], queryFn: () => api.get<Release[]>("/api/releases") });

export const useWhereUsed = (target: string, version: string) =>
  useQuery({
    queryKey: ["where-used", target, version],
    queryFn: () =>
      api.get<WhereUsed>(`/api/where-used?target=${target}&version=${encodeURIComponent(version)}`),
    enabled: Boolean(target && version),
  });
