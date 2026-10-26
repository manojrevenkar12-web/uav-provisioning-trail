import { Link, useParams } from "react-router-dom";

import { useCodeLabel } from "../../shared/api/codes";
import type { Certificate } from "../../shared/api/types";
import { clock, humanise, int, short } from "../../shared/lib/format";
import {
  Button,
  EmptyState,
  PageHeader,
  QueryView,
  Section,
  Skeleton,
  SkeletonBlock,
  Tag,
} from "../../shared/ui";
import { OWNER, TARGET, UNIT_STATUS } from "../../shared/theme/tokens";
import { useCertificate, useUnit } from "./api";
import { Trail } from "./Trail";
import styles from "./Units.module.css";

function download(cert: Certificate) {
  const blob = new Blob([JSON.stringify(cert, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${cert.certificate.unit}-software-certificate.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function CertificatePanel({ unit }: { unit: string }) {
  const q = useCertificate(unit, true);
  return (
    <QueryView query={q} skeleton={<SkeletonBlock label="Loading the certificate" rows={3} />}>
      {(c) => {
        const cert = c.certificate;
        const boot = cert.installed["orin_boot"] as
          { machine_id?: string; device_key_sha256?: string; l4t?: string } | undefined;
        return (
          <div className={styles.cert}>
            <dl className={styles.certGrid}>
              {(["fc", "pmu"] as const).map((t) => {
                const inst = cert.installed[t] as { version: string; sha256: string } | undefined;
                const board = cert.boards[t];
                return (
                  <div key={t}>
                    <dt>{TARGET[t]}</dt>
                    <dd>
                      <strong>{inst?.version}</strong> read back {short(inst?.sha256, 12)}
                      <span>
                        board rev {board?.board_rev}, lot {board?.lot}, uid {short(board?.uid, 12)}
                      </span>
                    </dd>
                  </div>
                );
              })}
              <div>
                <dt>{TARGET.orin}</dt>
                <dd>
                  <strong>
                    {String((cert.installed["orin"] as { version?: string } | undefined)?.version ?? "")}
                  </strong>{" "}
                  on L4T {boot?.l4t}
                  <span>
                    {cert.module
                      ? `SKU ${cert.module.sku}, FAB ${cert.module.fab}, batch ${cert.module.batch}, module ${cert.module.serial}`
                      : ""}
                  </span>
                  <span>
                    machine-id {short(boot?.machine_id, 12)}, device key {short(boot?.device_key_sha256, 12)}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Fuses</dt>
                <dd>
                  {cert.fuses
                    ? Object.entries(cert.fuses)
                        .map(([k, v]) => `${humanise(k)} ${v}`)
                        .join(", ")
                    : "none"}
                </dd>
              </div>
              <div>
                <dt>Signed</dt>
                <dd>
                  by station {cert.station} on {cert.slot}, {clock(cert.released_at)}
                  <span>trail head {short(cert.trail_head, 16)}</span>
                </dd>
              </div>
            </dl>
            <Button onClick={() => download(c)}>Download certificate</Button>
          </div>
        );
      }}
    </QueryView>
  );
}

function UnitSkeleton() {
  return (
    <div className={styles.page} role="status" aria-label="Loading the airframe">
      <Skeleton height="var(--text-3xl)" width="45%" />
      <SkeletonBlock label="Loading the trail" rows={6} />
    </div>
  );
}

export function UnitPage() {
  const { unit = "" } = useParams();
  const q = useUnit(unit);
  const codeLabel = useCodeLabel();
  return (
    <QueryView query={q} skeleton={<UnitSkeleton />}>
      {(d) => {
        const u = d.unit;
        return (
          <>
            <p className={styles.crumb}>
              <Link to="/units">Airframes</Link>
            </p>
            <PageHeader
              title={u.unit}
              lead={`${u.release ?? "no release"} on ${u.slot ?? "no slot"}, ${int(u.runs)} ${u.runs === 1 ? "run" : "runs"}, operator ${u.operator ?? "unknown"}.`}
              actions={
                <Tag tone={UNIT_STATUS[u.status]?.tone ?? "quiet"}>
                  {UNIT_STATUS[u.status]?.label ?? u.status}
                </Tag>
              }
            />
            <div className={styles.page}>
              <p className={d.chain.verified ? styles.verified : styles.broken} role="status">
                {d.chain.verified
                  ? `Trail verified: ${int(d.chain.events)} events, each signed by its station and linked to the one before.`
                  : `Trail does not verify: ${d.chain.problems.join("; ")}`}
              </p>
              {u.status === "held" && (
                <p className={styles.holdNote}>
                  Held at {u.step} for {OWNER[u.hold_owner ?? ""] ?? u.hold_owner}: {codeLabel(u.hold_code)}.
                </p>
              )}
              <div className={styles.split}>
                <Section title="Paper trail" lead="Exactly as the stations recorded it.">
                  {d.events.length ? (
                    <Trail events={d.events} />
                  ) : (
                    <EmptyState title="No events">Nothing recorded yet.</EmptyState>
                  )}
                </Section>
                <Section
                  title="Software certificate"
                  lead="What is on this airframe, signed by the station that released it."
                >
                  {u.status === "released" ? (
                    <CertificatePanel unit={u.unit} />
                  ) : (
                    <EmptyState title="Not released">
                      A certificate is signed when the last step passes.
                    </EmptyState>
                  )}
                </Section>
              </div>
            </div>
          </>
        );
      }}
    </QueryView>
  );
}
