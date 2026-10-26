import { useSearchParams } from "react-router-dom";

import { EmptyState, PageHeader, QueryView, SkeletonBlock, Tag } from "../../shared/ui";
import { Segmented } from "../../shared/ui/Segmented";
import { FINDING, STEP_INDEX, STEPS } from "../../shared/theme/tokens";
import { useReleases } from "../releases/api";
import { useInstructionCheck } from "./api";
import styles from "./Instructions.module.css";

export function InstructionsPage() {
  const [params, setParams] = useSearchParams();
  const releases = useReleases();
  const ids = (releases.data ?? []).map((r) => r.release);
  const release = params.get("release") ?? ids.at(-1) ?? "";
  const check = useInstructionCheck(release);
  return (
    <>
      <PageHeader
        title="Work instruction"
        lead="Does what the operator reads on the station screen match what the station does? Checked against the recipe and the release."
        actions={
          ids.length > 0 && (
            <Segmented
              label="Release"
              options={ids.map((r) => ({ value: r, label: r }))}
              value={release}
              onChange={(r) => setParams({ release: r }, { replace: true })}
            />
          )
        }
      />
      <QueryView query={check} skeleton={<SkeletonBlock label="Checking the instruction" rows={4} />}>
        {(c) => (
          <>
            <p className={styles.lead}>
              {c.document} revision {c.revision} against {c.release}:{" "}
              {c.findings.length === 0
                ? "they agree."
                : `${c.findings.length} ${c.findings.length === 1 ? "difference" : "differences"}.`}
            </p>
            {c.findings.length === 0 ? (
              <EmptyState title="The instruction matches">
                Every step the station runs is described, in order, with the versions it installs.
              </EmptyState>
            ) : (
              <ol className={styles.findings}>
                {c.findings.map((f) => {
                  const s = STEPS[STEP_INDEX[f.step] ?? -1];
                  return (
                    <li
                      key={`${f.kind}-${f.step}-${f.detail}`}
                      className={f.kind === "missing_warning" ? styles.irreversible : ""}
                    >
                      <Tag
                        tone={
                          f.kind === "missing_warning"
                            ? "orange"
                            : f.kind === "version_drift"
                              ? "bad"
                              : "watch"
                        }
                      >
                        {FINDING[f.kind] ?? f.kind}
                      </Tag>
                      <strong>
                        {s ? `${s.target ? s.target.toUpperCase() + " " : ""}${s.label}` : f.step}
                      </strong>
                      <p>{f.detail}</p>
                    </li>
                  );
                })}
              </ol>
            )}
          </>
        )}
      </QueryView>
    </>
  );
}
