import { useQuery } from "@tanstack/react-query";

import { humanise } from "../lib/format";
import { api } from "./client";

export type Codes = Record<string, { label: string; owner: string | null; signal: boolean }>;

/** The failure vocabulary, fetched once: every screen names a code the same way. */
export const useCodes = () =>
  useQuery({ queryKey: ["codes"], queryFn: () => api.get<Codes>("/api/codes"), staleTime: Infinity });

export function useCodeLabel(): (code: string | null | undefined) => string {
  const { data } = useCodes();
  return (code) => (code ? (data?.[code]?.label ?? humanise(code)) : "");
}
