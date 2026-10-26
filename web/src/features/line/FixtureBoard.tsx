import { Link } from "react-router-dom";

import { useCodeLabel } from "../../shared/api/codes";
import type { Issue, SlotState, Watch } from "../../shared/api/types";
import { minutes, num, pct, serialTail } from "../../shared/lib/format";
import { MOTION, STEP_INDEX, STEPS, UNIT_STATUS } from "../../shared/theme/tokens";
import styles from "./Line.module.css";
import { type RailState, StepRail } from "./StepRail";

function Socket({
  s,
  issues,
  watch,
  order,
}: {
  s: SlotState;
  issues: Issue[];
  watch?: Watch;
  order: number;
}) {
  const cur = s.current;
  const codeLabel = useCodeLabel();
  const state: RailState = cur ? (cur.status as RailState) : "empty";
  const systemic = issues.length > 0;
  const at = cur?.step ? STEPS[STEP_INDEX[cur.step] ?? -1] : undefined;
  return (
    <li className={`${styles.socket} ${systemic ? styles.flagged : ""}`}>
      <Link
        to={`/units?slot=${encodeURIComponent(s.slot)}`}
        className={styles.socketLink}
        aria-label={`Slot ${s.slot}: units`}
      >
        <div className={styles.socketHead}>
          <span className={styles.slotName}>Slot {s.index}</span>
          {systemic && (
            <span className={styles.systemicMark}>
              <span aria-hidden className={styles.orangeDot} />
              Systemic
            </span>
          )}
          {!systemic && watch && (
            <span className={styles.watchMark} title={watch.why}>
              USB2 links
            </span>
          )}
        </div>
        {cur ? (
          <>
            <div className={styles.unitLine}>
              <span className={styles.serial}>{serialTail(cur.unit)}</span>
              <span className={`${styles.state} ${styles[cur.status]}`}>
                {UNIT_STATUS[cur.status]?.label ?? cur.status}
              </span>
            </div>
            <p className={styles.stepLine}>
              {cur.status === "held"
                ? `${at?.target ? at.target.toUpperCase() + " " : ""}${at?.label ?? cur.step}: ${codeLabel(cur.hold_code)}`
                : cur.status === "in_progress"
                  ? `${at?.target ? at.target.toUpperCase() + " " : ""}${at?.label ?? cur.step}`
                  : `${cur.release} installed`}
            </p>
          </>
        ) : (
          <p className={styles.stepLine}>No airframe yet this shift</p>
        )}
        <StepRail state={state} step={cur?.step ?? null} delay={order * MOTION.stagger * 2} />
        {s.recent.length > 0 && (
          <ol
            className={styles.recent}
            aria-label={`Last ${s.recent.length} airframes on this slot, oldest first`}
          >
            {s.recent.map((r) => (
              <li
                key={r.unit}
                className={`${styles.pip} ${styles[r.status]}`}
                title={`${r.unit}: ${r.status}${r.hold_code ? `, ${r.hold_code}` : ""}`}
              >
                <span className="visually-hidden">
                  {r.unit} {r.status}
                </span>
              </li>
            ))}
          </ol>
        )}
        {s.stats && (
          <dl className={styles.socketStats}>
            <div>
              <dt>First pass</dt>
              <dd>{s.stats.first_pass_yield != null ? pct(num(s.stats.first_pass_yield), 0) : "n/a"}</dd>
            </div>
            <div>
              <dt>Lost</dt>
              <dd>{minutes(s.stats.lost_minutes)}</dd>
            </div>
            <div>
              <dt>Units</dt>
              <dd>{s.stats.units}</dd>
            </div>
          </dl>
        )}
        {systemic && <p className={styles.issueLine}>{issues.map((i) => i.label).join("; ")}</p>}
      </Link>
    </li>
  );
}

/**
 * The line as it stands: every fixture as a plate with its slots, each showing the airframe on it, where it is
 * in the recipe, the last airframes it handled and how the slot is doing. A slot a systemic issue points at is
 * ringed in orange; a slot whose cable is going bad is marked before it starts failing.
 */
export function FixtureBoard({
  slots,
  issues,
  watch,
}: {
  slots: SlotState[];
  issues: Issue[];
  watch: Watch[];
}) {
  const bySlot = new Map<string, Issue[]>();
  for (const i of issues) {
    if (i.kind !== "systemic") continue;
    for (const w of i.where)
      if (w.dimension === "slot") bySlot.set(w.value, [...(bySlot.get(w.value) ?? []), i]);
  }
  const watchBySlot = new Map(watch.map((w) => [w.slot, w]));
  const fixtures = [...new Set(slots.map((s) => s.fixture))];
  let order = 0;
  return (
    <div className={styles.board}>
      {fixtures.map((f) => {
        const own = slots.filter((s) => s.fixture === f);
        return (
          <section key={f} className={styles.plate} aria-labelledby={`plate-${f}`}>
            <h2 id={`plate-${f}`} className={styles.plateTitle}>
              {f} <span>{own[0]?.station}</span>
            </h2>
            <ul className={styles.sockets}>
              {own.map((s) => (
                <Socket
                  key={s.slot}
                  s={s}
                  issues={bySlot.get(s.slot) ?? []}
                  watch={watchBySlot.get(s.slot)}
                  order={order++}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
