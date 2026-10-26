import { motion } from "framer-motion";

import { useCodeLabel } from "../../shared/api/codes";
import type { TrailEvent } from "../../shared/api/types";
import { humanise, short, time } from "../../shared/lib/format";
import { MOTION, STEP_INDEX, STEPS } from "../../shared/theme/tokens";
import styles from "./Units.module.css";

function stepName(id: string | undefined) {
  const s = id ? STEPS[STEP_INDEX[id] ?? -1] : undefined;
  return s ? `${s.target ? s.target.toUpperCase() + " " : ""}${s.label}` : (id ?? "");
}

function describe(
  e: TrailEvent,
  codeLabel: (c: string | undefined) => string,
): { title: string; detail: string; tone: string } {
  const d = e.data;
  switch (e.kind) {
    case "start":
      return {
        title: `Run started on ${String(d["slot"])}`,
        detail: `${String(d["release"])}, recipe ${String(d["recipe"])}, ${String(d["operator"])}`,
        tone: "start",
      };
    case "intent":
      return {
        title: `${stepName(d.step)}, attempt ${d.attempt}`,
        detail: "announced before it ran",
        tone: "intent",
      };
    case "result":
      return d.ok
        ? { title: `${stepName(d.step)} passed`, detail: `${d.seconds ?? 0} s`, tone: "ok" }
        : {
            title: `${stepName(d.step)} failed: ${codeLabel(d.code)}`,
            detail: String(d.detail ?? ""),
            tone: "failed",
          };
    case "recovery":
      return {
        title: `Recovery: ${humanise(d.action ?? "")}`,
        detail: `then again from ${stepName(String(d["restart_at"]))}`,
        tone: "recovery",
      };
    case "hold":
      return {
        title: `Held for ${humanise(String(d["owner"]))}: ${codeLabel(d.code)}`,
        detail: String(d.detail ?? ""),
        tone: "failed",
      };
  }
}

/**
 * The unit's paper trail as it is stored: every event linked to the one before it by hash. Intent events are
 * folded into their results unless a result never came (a crash or a pulled cable mid-step).
 */
export function Trail({ events }: { events: TrailEvent[] }) {
  const codeLabel = useCodeLabel();
  const resulted = new Set(
    events.filter((e) => e.kind === "result").map((e) => `${e.data.step}:${e.data.attempt}`),
  );
  const shown = events.filter(
    (e) => e.kind !== "intent" || !resulted.has(`${e.data.step}:${e.data.attempt}`),
  );
  return (
    <ol className={styles.trail}>
      {shown.map((e, i) => {
        const d = describe(e, codeLabel);
        const orphan = e.kind === "intent";
        return (
          <motion.li
            key={e.seq}
            className={`${styles.event} ${styles[d.tone]}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: MOTION.quick, delay: Math.min(i, 30) * 0.01 }}
          >
            <span className={styles.node} aria-hidden />
            <div className={styles.eventBody}>
              <div className={styles.eventHead}>
                <strong>{orphan ? `${d.title}: no result recorded` : d.title}</strong>
                <time dateTime={e.at}>{time(e.at)}</time>
              </div>
              {d.detail && <p>{d.detail}</p>}
              <p className={styles.hashes}>
                #{e.seq} {short(e.hash, 12)} <span>follows {short(e.prev, 8)}</span>
              </p>
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
