import { motion } from "framer-motion";

import { MOTION, STEP_INDEX, STEPS } from "../../shared/theme/tokens";
import styles from "./Line.module.css";

export type RailState = "released" | "held" | "in_progress" | "empty";

/**
 * The recipe as a rail of segments, one per step: done, failed, running or not reached. The step that cannot be
 * undone (the fuse burn) carries an orange notch, so nobody pulls a module there by surprise.
 */
export function StepRail({
  state,
  step,
  delay = 0,
}: {
  state: RailState;
  step: string | null;
  delay?: number;
}) {
  const at = step ? (STEP_INDEX[step] ?? -1) : -1;
  const label =
    state === "released"
      ? "every step done"
      : state === "held"
        ? `held at ${STEPS[at]?.label ?? step}`
        : state === "in_progress"
          ? `running ${STEPS[at]?.label ?? step}`
          : "no unit";
  return (
    <div className={styles.rail} role="img" aria-label={`Steps: ${label}`}>
      {STEPS.map((s, i) => {
        const cls =
          state === "released"
            ? styles.done
            : state === "empty"
              ? styles.todo
              : i < at
                ? styles.done
                : i === at
                  ? state === "held"
                    ? styles.failed
                    : styles.running
                  : styles.todo;
        return (
          <motion.span
            key={s.id}
            className={`${styles.segment} ${cls} ${s.irreversible ? styles.irreversible : ""}`}
            title={`${s.target ? s.target.toUpperCase() + " " : ""}${s.label}`}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: MOTION.quick, ease: MOTION.ease, delay: delay + i * MOTION.stagger }}
          />
        );
      })}
    </div>
  );
}
