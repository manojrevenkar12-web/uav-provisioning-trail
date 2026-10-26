import type { Role } from "../theme/tokens";
import type { Problem } from "./types";

const TOKEN_KEY = "uav.token";
const ROLE_KEY = "uav.role";
const ACTOR_KEY = "uav.actor";

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* private mode: kept until reload */
  }
}

const listeners = new Set<() => void>();
const changed = () => listeners.forEach((l) => l());
let memory: Record<string, string> = {};

const get = (key: string) => read(key) ?? memory[key] ?? null;
const put = (key: string, value: string) => {
  memory = { ...memory, [key]: value };
  write(key, value);
  changed();
};

/**
 * Who is asking. With UAV_API_TOKENS set the token decides the role and the name; in development the console
 * sends the role and name chosen in the header. Kept for this tab only.
 */
export const session = {
  token: () => get(TOKEN_KEY),
  setToken: (t: string) => put(TOKEN_KEY, t.trim()),
  role: (): Role => (get(ROLE_KEY) as Role | null) ?? "lead",
  setRole: (r: Role) => put(ROLE_KEY, r),
  actor: () => get(ACTOR_KEY) ?? "",
  setActor: (a: string) => put(ACTOR_KEY, a.trim()),
  subscribe: (l: () => void) => {
    listeners.add(l);
    return () => void listeners.delete(l);
  },
  /** Tests start each case from nothing. */
  reset: () => {
    memory = {};
    changed();
  },
};

/** An API failure with what the API said about it (problem details) and whether trying again may help. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly title: string,
    readonly detail?: string,
  ) {
    super(detail ? `${title}: ${detail}` : title);
  }

  get retryable() {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }

  get needsToken() {
    return this.status === 401;
  }
}

async function send(method: string, path: string, json?: unknown): Promise<Response> {
  const headers: Record<string, string> = { accept: "application/json", "x-uav-role": session.role() };
  const actor = session.actor();
  if (actor) headers["x-uav-actor"] = actor;
  const t = session.token();
  if (t) headers["authorization"] = `Bearer ${t}`;
  if (json !== undefined) headers["content-type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: json === undefined ? undefined : JSON.stringify(json),
    });
  } catch {
    throw new ApiError(
      0,
      "The traceability server cannot be reached",
      "Check that `uavtrail serve` is running.",
    );
  }
  if (!response.ok) {
    let problem: Partial<Problem> = {};
    try {
      problem = (await response.json()) as Problem;
    } catch {
      /* no body */
    }
    const title =
      problem.title ??
      (response.status === 401 ? "The API needs a token" : `The API answered ${response.status}`);
    throw new ApiError(response.status, title, problem.detail);
  }
  return response;
}

export const api = {
  get: async <T>(path: string) => (await (await send("GET", path)).json()) as T,
  post: async <T>(path: string, json: unknown) => (await (await send("POST", path, json)).json()) as T,
};
