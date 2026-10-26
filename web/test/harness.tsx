/** Renders the real routes against a stubbed API and records what the console sent. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MotionConfig } from "framer-motion";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "../src/app/App";

export type Reply = unknown | Response | ((url: string, init?: RequestInit) => unknown | Response);
export type Routes = Record<string, Reply>;

export const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });

export const problem = (status: number, title: string, detail?: string) =>
  json({ status, title, detail }, status);

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

/**
 * Routes keyed "GET /api/x" (any query) or "GET /api/x?a=b" (that query only); a missing route answers 404 so a
 * test sees what it forgot to stub.
 */
export function stubApi(routes: Routes): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const headers = (init?.headers ?? {}) as Record<string, string>;
      let body: unknown = init?.body;
      if (typeof body === "string") body = JSON.parse(body);
      calls.push({ method, path: input, body, headers });
      const reply = routes[`${method} ${input}`] ?? routes[`${method} ${input.split("?")[0]}`];
      if (reply === undefined) return problem(404, `no stub for ${method} ${input}`);
      const value = await (typeof reply === "function"
        ? (reply as (u: string, i?: RequestInit) => unknown)(input, init)
        : reply);
      return value instanceof Response ? value : json(value);
    }),
  );
  return calls;
}

export function renderAt(path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MotionConfig reducedMotion="always">
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </MotionConfig>
    </QueryClientProvider>,
  );
}

export const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
