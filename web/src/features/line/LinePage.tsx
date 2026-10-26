import { motion } from "framer-motion";
import { Link } from "react-router-dom";

import { useCodeLabel } from "../../shared/api/codes";
import type { Overview } from "../../shared/api/types";
import { clock, int, minutes, num, pct } from "../../shared/lib/format";
import { EmptyState, Figure, PageHeader, QueryView, Section, Skeleton, Tag } from "../../shared/ui";
import { DIMENSION, ISSUE_KIND, MOTION, OWNER } from "../../shared/theme/tokens";
import { useIssues } from "../issues/api";
import { useOverview, useSlots } from "./api";
import { FixtureBoard } from "./FixtureBoard";
import styles from "./Line.module.css";

function Kpis({ o }: { o: Overview }) {
  const k = o.kpis;
  return (
    <div className={styles.kpis}>
      <Figure
        label="Software first-pass yield"
        value={k.first_pass_yield.value != null ? pct(k.first_pass_yield.value) : "n/a"}
        note={`${int(k.first_pass_yield.count)} of ${int(k.first_pass_yield.of)} airframes, no failed step`}
      />
      <Figure
        label="Flash success"
        value={k.flash_success.value != null ? pct(k.flash_success.value) : "n/a"}
        note={`${int(k.flash_success.count)} of ${int(k.flash_success.of)} program and image flashes`}
      />
      <Figure
        label="Downtime"
        value={minutes(k.downtime_minutes)}
        note="slot time lost to failures, recoveries and holds"
      />
      <Figure
        label="Final yield"
        value={k.final_yield.value != null ? pct(k.final_yield.value) : "n/a"}
        note={`${int(k.units.released)} released, ${int(k.units.held)} held, ${int(k.units.reworked)} reworked`}
      />
      <Figure
        label="Cycle time"
        value={k.cycle_minutes_median != null ? minutes(k.cycle_minutes_median) : "n/a"}
        note="median, start to release"
      />
    </div>
  );
}

function Systemic({ o }: { o: Overview }) {
  if (o.systemic.length === 0)
    return (
      <EmptyState title="Nothing systemic">
        Every failure so far is one-off.{" "}
        {o.one_off > 0 && `${int(o.one_off)} failures, spread across the line.`}
      </EmptyState>
    );
  return (
    <ol className={styles.issueList}>
      {o.systemic.map((i, n) => (
        <motion.li
          key={i.key}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: MOTION.move, ease: MOTION.ease, delay: n * MOTION.stagger * 3 }}
        >
          <Link to={`/issues#${i.key}`} className={styles.issueLink}>
            <Tag tone={ISSUE_KIND[i.kind]?.tone ?? "quiet"}>{ISSUE_KIND[i.kind]?.label}</Tag>
            <strong>{i.label}</strong>
            <span className={styles.issueWhere}>
              {i.where.length
                ? i.where.map((w) => `${DIMENSION[w.dimension] ?? w.dimension} ${w.value}`).join(", ")
                : "everywhere"}
            </span>
            <span className={styles.issueMeta}>
              {int(i.failures)} failures, {minutes(i.lost_minutes)} lost, {OWNER[i.owner] ?? i.owner}
            </span>
          </Link>
        </motion.li>
      ))}
    </ol>
  );
}

function Pareto({ o }: { o: Overview }) {
  const codeLabel = useCodeLabel();
  if (o.pareto.length === 0)
    return <EmptyState title="No failures">Every step passed at its first attempt.</EmptyState>;
  const top = Math.max(...o.pareto.map((p) => p.failures));
  return (
    <ul className={styles.pareto} aria-label="Failures by code">
      {o.pareto.map((p, n) => (
        <li key={p.code}>
          <span className={styles.paretoCode} title={p.code}>
            {codeLabel(p.code)}
          </span>
          <span className={styles.paretoBar}>
            <motion.span
              initial={{ width: 0 }}
              animate={{ width: `${(p.failures / top) * 100}%` }}
              transition={{ duration: MOTION.draw, ease: MOTION.ease, delay: n * MOTION.stagger }}
            />
          </span>
          <span className={styles.paretoN}>
            {int(p.failures)} <small>{minutes(num(p.lost_minutes))}</small>
          </span>
        </li>
      ))}
    </ul>
  );
}

function LineSkeleton() {
  return (
    <div className={styles.skeleton} role="status" aria-label="Loading the line">
      <Skeleton height="var(--text-3xl)" width="40%" />
      <Skeleton height="6rem" />
      <div className={styles.board}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} height="16rem" />
        ))}
      </div>
    </div>
  );
}

function Board() {
  const slots = useSlots();
  const issues = useIssues();
  return (
    <QueryView
      query={slots}
      skeleton={<Skeleton height="30rem" />}
      isEmpty={(s) => s.length === 0}
      empty={
        <EmptyState title="No fixtures configured">Add stations and fixtures in config/line.yaml.</EmptyState>
      }
    >
      {(s) => <FixtureBoard slots={s} issues={issues.data?.issues ?? []} watch={issues.data?.watch ?? []} />}
    </QueryView>
  );
}

export function LinePage() {
  const overview = useOverview();
  return (
    <QueryView
      query={overview}
      skeleton={<LineSkeleton />}
      isEmpty={(o) => o.kpis.units.started === 0}
      empty={
        <EmptyState title="No airframe has started yet">
          The board fills as stations send their trail. On the emulated line:{" "}
          <code>uavsim run campaigns/dev/shift-a.yaml</code>.
        </EmptyState>
      }
    >
      {(o) => (
        <>
          <PageHeader
            title="The line"
            lead={`${int(o.kpis.units.started)} airframes from ${clock(o.kpis.window.from)} to ${clock(o.kpis.window.to)}. Refreshes on its own.`}
          />
          <Kpis o={o} />
          <div className={styles.layout}>
            <Section title="Fixtures" lead="Click a slot for its airframes.">
              <Board />
            </Section>
            <aside className={styles.side}>
              <Section title="Systemic now" actions={<Link to="/issues">All issues</Link>}>
                <Systemic o={o} />
              </Section>
              {o.watch.length > 0 && (
                <Section title="Watch" lead="Not failing yet, but these come before failures.">
                  <ul className={styles.watchList}>
                    {o.watch.map((w) => (
                      <li key={w.slot}>
                        <Tag tone="signal">{w.slot}</Tag> {pct(w.share, 0)} of {int(w.units)} modules link at
                        USB2.
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
              <Section title="Failures by code">
                <Pareto o={o} />
              </Section>
            </aside>
          </div>
        </>
      )}
    </QueryView>
  );
}
