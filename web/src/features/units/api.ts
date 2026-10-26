import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api/client";
import type { Certificate, UnitDetail, UnitRow } from "../../shared/api/types";

export const PAGE = 30;

export interface UnitFilter {
  status?: string;
  slot?: string;
  code?: string;
  q?: string;
  page: number;
}

export function unitsPath(f: UnitFilter) {
  const p = new URLSearchParams();
  if (f.status) p.set("status", f.status);
  if (f.slot) p.set("slot", f.slot);
  if (f.code) p.set("code", f.code);
  if (f.q) p.set("q", f.q);
  p.set("limit", String(PAGE));
  p.set("offset", String(f.page * PAGE));
  return `/api/units?${p.toString()}`;
}

export const useUnits = (f: UnitFilter) =>
  useQuery({
    queryKey: ["units", f],
    queryFn: () => api.get<{ total: number; rows: UnitRow[] }>(unitsPath(f)),
    placeholderData: (x) => x,
  });

export const useUnit = (unit: string) =>
  useQuery({
    queryKey: ["unit", unit],
    queryFn: () => api.get<UnitDetail>(`/api/units/${encodeURIComponent(unit)}`),
  });

export const useCertificate = (unit: string, enabled: boolean) =>
  useQuery({
    queryKey: ["certificate", unit],
    queryFn: () => api.get<Certificate>(`/api/units/${encodeURIComponent(unit)}/certificate`),
    enabled,
  });
