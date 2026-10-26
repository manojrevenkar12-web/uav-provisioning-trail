import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api/client";
import type { InstructionCheck } from "../../shared/api/types";

export const useInstructionCheck = (release: string) =>
  useQuery({
    queryKey: ["instructions", release],
    queryFn: () => api.get<InstructionCheck>(`/api/instructions?release=${encodeURIComponent(release)}`),
    enabled: Boolean(release),
  });
