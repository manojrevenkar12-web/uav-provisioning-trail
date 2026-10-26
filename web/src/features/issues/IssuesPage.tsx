import { motion } from "framer-motion";
import { Link } from "react-router-dom";

import type { Issue, Watch } from "../../shared/api/types";
import { clock, humanise, int, minutes, pct } from "../../shared/lib/format";
import { EmptyState, PageHeader, QueryView, Section, SkeletonBlock, Tag } from "../../shared/ui";
import { DIMENSION, ISSUE_KIND, MOTION, OWNER } from "../../shared/theme/tokens";
import { ActOnIssue } from "./ActOnIssue";
import { useIssues } from "./api";
import styles from "./Issues.module.css";

/** A p-value as odds a person can weigh: "1 in 4.8 million". */
export function odds(p: number | null): string {
  if (p == null) return "";
  if (p <= 0) return "practically impossible by chance";
  const n = 1 / p;
  if (n < 1000) return `1 in ${Math.round(n)} by chance`;
  if (n < 1e6) return `1 in ${Math.round(n / 1000)} thousand by chance`;
  if (n < 1e9) return `1 in ${(n / 1e6).toFixed(1)} million by chance`;
  return "less than 1 in a billion by chance";
}

function Where({ issue }: { issue: Issue }) {
  if (issue.where.length === 0) return <span className={styles.nowhere}>No single place</span>;
  return (
    <span className={styles.where}>
      {issue.where.map((w) => (
        <span key={w.dimension} className={styles.place}>
          <small>{DIMENSION[w.dimension] ?? w.dimension}</small> {w.value}
        </span>
      ))}
    </span>
  );
}

function IssueCard({ issue, n }: { issue: Issue; n: number }) {
  const kind = ISSUE_KIND[issue.kind];
  const unitsLink =
    issue.where[0]?.dimension === "slot" ? `/units?slot=${encodeURIComponent(issue.where[0].value)}` : null;
  return (
    <motion.article
      id={issue.key}
      className={`${styles.card} ${styles[issue.kind]}`}
      aria-labelledby={`i-${issue.key}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: MOTION.move, ease: MOTION.ease, delay: Math.min(n, 8) * MOTION.stagger * 2 }}
    >
      <header className={styles.cardHead}>
        <Tag tone={kind?.tone ?? "quiet"} title={kind?.means}>
          {kind?.label}
        </Tag>
        <h3 id={`i-${issue.key}`}>{issue.label}</h3>
        <code>{issue.code}</code>
      </header>
      <Where issue={issue} />
      <dl className={styles.facts}>
        <div>
          <dt>Failures</dt>
          <dd>
            {int(issue.failures)} of {int(issue.attempts)} tries, {int(issue.units)} airframes
          </dd>
        </div>
        {issue.rest_rate != null && (
          <div>
            <dt>Rate</dt>
            <dd>
              {pct(issue.rate)} here, {pct(issue.rest_rate)} elsewhere <small>({odds(issue.p_value)})</small>
            </dd>
          </div>
        )}
        <div>
          <dt>Lost</dt>
          <dd>{minutes(issue.lost_minutes)}</dd>
        </div>
        <div>
          <dt>Seen</dt>
          <dd>
            {clock(issue.first_seen)} to {clock(issue.last_seen)}
          </dd>
        </div>
        <div>
          <dt>Owner</dt>
          <dd>{OWNER[issue.owner] ?? issue.owner}</dd>
        </div>
      </dl>
      <p className={styles.action}>{issue.action}</p>
      {issue.effect && (
        <p className={`${styles.effect} ${styles[issue.effect.verdict.replace(/ /g, "_")]}`}>
          Fixed {clock(issue.effect.since)}: {pct(issue.effect.before.rate ?? 0)} before,{" "}
          {issue.effect.after.attempts ? pct(issue.effect.after.rate ?? 0) : "no tries yet"} after.{" "}
          <strong>{humanise(issue.effect.verdict)}.</strong>
        </p>
      )}
      {issue.actions && issue.actions.length > 0 && (
        <ol className={styles.history} aria-label="What was done">
          {issue.actions.map((a) => (
            <li key={a.id}>
              <strong>{humanise(a.action)}</strong> by {a.actor}, {clock(a.at)}: {a.note}
            </li>
          ))}
        </ol>
      )}
      <footer className={styles.cardFoot}>
        <span className={styles.examples}>
          {issue.examples.slice(0, 3).map((u) => (
            <Link key={u} to={`/units/${u}`}>
              {u}
            </Link>
          ))}
        </span>
        {unitsLink && <Link to={unitsLink}>Every airframe on this slot</Link>}
        <ActOnIssue issue={issue} />
      </footer>
    </motion.article>
  );
}

function WatchList({ watch }: { watch: Watch[] }) {
  return (
    <ul className={styles.watch}>
      {watch.map((w) => (
        <li key={w.slot}>
          <Tag tone="signal">{w.slot}</Tag>
          <span>
            {pct(w.share, 0)} of {int(w.units)} modules link at USB2 (between {pct(w.interval[0], 0)} and{" "}
            {pct(w.interval[1], 0)}). {w.why.charAt(0).toUpperCase() + w.why.slice(1)}.
          </span>
        </li>
      ))}
    </ul>
  );
}

export function IssuesPage() {
  const q = useIssues();
  return (
    <>
      <PageHeader
        title="Issues"
        lead="Failures grouped by code. A code is systemic where one place (a slot, a lot, a release, an operator) fails it far more often than the rest of the line, beyond what chance explains; everything else is one-off."
      />
      <QueryView
        query={q}
        skeleton={<SkeletonBlock label="Loading the issues" rows={4} height="10rem" />}
        isEmpty={(d) => d.issues.length === 0 && d.watch.length === 0}
        empty={<EmptyState title="No failures yet">Every step has passed at its first attempt.</EmptyState>}
      >
        {(d) => {
          const groups = (["systemic", "widespread", "one_off"] as const).map(
            (k) => [k, d.issues.filter((i) => i.kind === k)] as const,
          );
          let n = 0;
          return (
            <div className={styles.page}>
              {d.watch.length > 0 && (
                <Section title="Watch" lead="Leading signals: not failures yet.">
                  <WatchList watch={d.watch} />
                </Section>
              )}
              {groups.map(([k, list]) =>
                list.length === 0 ? null : (
                  <Section
                    key={k}
                    title={`${ISSUE_KIND[k]?.label} (${list.length})`}
                    lead={ISSUE_KIND[k]?.means}
                  >
                    <div className={styles.cards}>
                      {list.map((i) => (
                        <IssueCard key={i.key} issue={i} n={n++} />
                      ))}
                    </div>
                  </Section>
                ),
              )}
            </div>
          );
        }}
      </QueryView>
    </>
  );
}
