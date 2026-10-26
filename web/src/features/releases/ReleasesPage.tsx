import { useState } from "react";
import { Link } from "react-router-dom";

import type { Release } from "../../shared/api/types";
import { clock, int } from "../../shared/lib/format";
import { EmptyState, PageHeader, QueryView, Section, SkeletonBlock, Table, ui } from "../../shared/ui";
import { Segmented } from "../../shared/ui/Segmented";
import { TARGET } from "../../shared/theme/tokens";
import { useReleases, useWhereUsed } from "./api";
import styles from "./Releases.module.css";

function ReleaseCard({ r }: { r: Release }) {
  const released = r.units.released ?? 0;
  const held = r.units.held ?? 0;
  return (
    <article className={styles.card} aria-labelledby={`r-${r.release}`}>
      <h3 id={`r-${r.release}`}>{r.release}</h3>
      <dl className={styles.facts}>
        {Object.entries(r.artifacts).map(([t, v]) => (
          <div key={t}>
            <dt>{TARGET[t] ?? t}</dt>
            <dd>{v}</dd>
          </div>
        ))}
        <div>
          <dt>FC boards</dt>
          <dd>rev {r.compatible.fc.join(", ")}</dd>
        </div>
        <div>
          <dt>Modules</dt>
          <dd>
            SKU {r.compatible.orin.sku.join(", ")}, FAB {r.compatible.orin.fab.join(", ")}
          </dd>
        </div>
      </dl>
      <p className={styles.rollout}>
        <strong>{int(released)}</strong> released, <strong>{int(held)}</strong> held
      </p>
      <Link to={`/instructions?release=${r.release}`}>Check the work instruction against it</Link>
    </article>
  );
}

function WhereUsed({ releases }: { releases: Release[] }) {
  const targets = [
    { value: "fc", label: TARGET.fc! },
    { value: "pmu", label: TARGET.pmu! },
    { value: "orin", label: TARGET.orin! },
  ];
  const [target, setTarget] = useState("fc");
  const versions = [...new Set(releases.map((r) => r.artifacts[target]).filter(Boolean))] as string[];
  const [version, setVersion] = useState<string>("");
  const v = versions.includes(version) ? version : (versions.at(-1) ?? "");
  const q = useWhereUsed(target, v);
  return (
    <>
      <div className={styles.controls}>
        <Segmented label="Target" options={targets} value={target} onChange={setTarget} />
        <label className={styles.select}>
          <span>Version</span>
          <select className={ui.input} value={v} onChange={(e) => setVersion(e.target.value)}>
            {versions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
      </div>
      <QueryView
        query={q}
        skeleton={<SkeletonBlock label="Looking for airframes" rows={4} height="var(--space-6)" />}
        isEmpty={(d) => d.units.length === 0}
        empty={
          <EmptyState title="No released airframe carries it">Nothing to recall for this version.</EmptyState>
        }
      >
        {(d) => (
          <>
            <p className={styles.count}>
              {int(d.units.length)} released airframes carry {TARGET[d.target]} {d.version}.
            </p>
            <Table caption={`Airframes with ${d.target} ${d.version}`}>
              <thead>
                <tr>
                  <th scope="col">Serial</th>
                  <th scope="col">Release</th>
                  <th scope="col">Slot</th>
                  <th scope="col">Released</th>
                </tr>
              </thead>
              <tbody>
                {d.units.slice(0, 50).map((u) => (
                  <tr key={u.unit}>
                    <td>
                      <Link to={`/units/${u.unit}`}>{u.unit}</Link>
                    </td>
                    <td>{u.release}</td>
                    <td>{u.slot}</td>
                    <td>{clock(u.released_at)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {d.units.length > 50 && (
              <p className={styles.count}>Showing the first 50; the API returns all of them.</p>
            )}
          </>
        )}
      </QueryView>
    </>
  );
}

export function ReleasesPage() {
  const q = useReleases();
  return (
    <>
      <PageHeader
        title="Releases"
        lead="What release engineering signed for the line, how far each has rolled out, and which airframes carry a given version."
      />
      <QueryView
        query={q}
        skeleton={<SkeletonBlock label="Loading the releases" rows={2} height="12rem" />}
        isEmpty={(r) => r.length === 0}
        empty={
          <EmptyState title="No releases">
            Releases live in releases/*.yaml and are signed with uavtrail release build.
          </EmptyState>
        }
      >
        {(rs) => (
          <div className={styles.page}>
            <div className={styles.cards}>
              {rs.map((r) => (
                <ReleaseCard key={r.release} r={r} />
              ))}
            </div>
            <Section
              title="Where used"
              lead="The recall list: every released airframe carrying a version, from the signed certificates."
            >
              <WhereUsed releases={rs} />
            </Section>
          </div>
        )}
      </QueryView>
    </>
  );
}
