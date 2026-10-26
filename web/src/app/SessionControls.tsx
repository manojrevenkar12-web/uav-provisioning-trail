import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { session } from "../shared/api/client";
import { useDebounced } from "../shared/lib/useDebounced";
import { useSession } from "../shared/lib/useSession";
import { ROLES, type Role } from "../shared/theme/tokens";
import styles from "./Shell.module.css";

/**
 * Who the console acts as. In development the API takes the role and name from headers; with UAV_API_TOKENS
 * set, the token decides and these only change what the console offers.
 */
export function SessionControls() {
  const { role, actor } = useSession();
  const qc = useQueryClient();
  const [name, setName] = useState(actor);
  const settled = useDebounced(name);
  useEffect(() => {
    if (settled.trim() !== session.actor()) session.setActor(settled);
  }, [settled]);

  return (
    <div className={styles.session}>
      <label className={styles.control}>
        <span>Acting as</span>
        <select
          value={role}
          onChange={(e) => {
            session.setRole(e.target.value as Role);
            void qc.invalidateQueries();
          }}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.control}>
        <span>Your name</span>
        <input
          value={name}
          placeholder="for the issue log"
          autoComplete="name"
          onChange={(e) => setName(e.target.value)}
        />
      </label>
    </div>
  );
}
