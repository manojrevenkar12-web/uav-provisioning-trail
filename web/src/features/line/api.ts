import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api/client";
import type { Overview, SlotState } from "../../shared/api/types";
import { LIVE_REFRESH_MS } from "../../shared/theme/tokens";

export const useOverview = () =>
  useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<Overview>("/api/overview"),
    refetchInterval: LIVE_REFRESH_MS,
  });

export const useSlots = () =>
  useQuery({
    queryKey: ["slots"],
    queryFn: () => api.get<SlotState[]>("/api/slots"),
    refetchInterval: LIVE_REFRESH_MS,
  });
