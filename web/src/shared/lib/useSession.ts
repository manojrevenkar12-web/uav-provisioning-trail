import { useSyncExternalStore } from "react";

import { session } from "../api/client";
import type { Role } from "../theme/tokens";

/** The role and name the console acts as; every screen re-renders when they change. */
export function useSession(): { role: Role; actor: string } {
  const role = useSyncExternalStore(session.subscribe, session.role, session.role);
  const actor = useSyncExternalStore(session.subscribe, session.actor, session.actor);
  return { role, actor };
}

export const canActOnIssues = (role: Role) => role === "lead" || role === "engineering" || role === "quality";
