import { Link, useSearchParams } from "react-router-dom";

import { useCodeLabel } from "../../shared/api/codes";
import { clock, int } from "../../shared/lib/format";
import { useDebounced } from "../../shared/lib/useDebounced";
import { Button, EmptyState, PageHeader, QueryView, SkeletonBlock, Table, Tag, ui } from "../../shared/ui";
import { Segmented } from "../../shared/ui/Segmented";
import { OWNER, STEP_INDEX, STEPS, UNIT_STATUS } from "../../shared/theme/tokens";
import { PAGE, useUnits } from "./api";
import styles from "./Units.module.css";

const STATUSES = [
  { value: "", label: "All" },
  { value: "held", label: "Held" },
  { value: "released", label: "Released" },
  { value: "in_progress", label: "On a fixture" },
];

export function UnitsPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const slot = params.get("slot") ?? "";
  const code = params.get("code") ?? "";
  const q = params.get("q") ?? "";
  const page = Math.max(Number(params.get("page") ?? 0) || 0, 0);
  const search = useDebounced(q.trim());
  const codeLabel = useCodeLabel();
  const units = useUnits({
    status: status || undefined,
    slot: slot || undefined,
    code: code || undefined,
    q: search || undefined,
    page,
  });

  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader
        title="Airframes"
        lead={
          slot
            ? `Every airframe that went through slot ${slot}.`
            : "Every airframe the stations have reported, newest first."
        }
      />
      <div className={styles.filters}>
        <Segmented label="Status" options={STATUSES} value={status} onChange={(v) => set({ status: v })} />
        <label className={styles.search}>
          <span>Find a serial</span>
          <input
            className={ui.input}
            type="search"
            value={q}
            placeholder="HX2-26-…"
            onChange={(e) => set({ q: e.target.value })}
          />
        </label>
        {(slot || code) && (
          <Button variant="quiet" onClick={() => set({ slot: "", code: "" })}>
            {slot ? `Slot ${slot}` : codeLabel(code)}: show every slot
          </Button>
        )}
      </div>
      <QueryView
        query={units}
        skeleton={<SkeletonBlock label="Loading the airframes" rows={8} height="var(--space-6)" />}
        isEmpty={(d) => d.rows.length === 0}
        empty={
          <EmptyState
            title="No airframe matches"
            action={<Button onClick={() => setParams({}, { replace: true })}>Clear the filters</Button>}
          >
            {q ? `No serial contains “${q}”.` : "Try another status or slot."}
          </EmptyState>
        }
      >
        {(d) => (
          <>
            <Table caption="Airframes">
              <thead>
                <tr>
                  <th scope="col">Serial</th>
                  <th scope="col">Status</th>
                  <th scope="col">Where it stopped</th>
                  <th scope="col">Release</th>
                  <th scope="col">Slot</th>
                  <th scope="col" className={ui.num}>
                    Runs
                  </th>
                  <th scope="col">Last event</th>
                </tr>
              </thead>
              <tbody>
                {d.rows.map((u) => {
                  const step = u.step ? STEPS[STEP_INDEX[u.step] ?? -1] : undefined;
                  return (
                    <tr key={u.unit}>
                      <td>
                        <Link to={`/units/${u.unit}`} className={styles.serial}>
                          {u.unit}
                        </Link>
                      </td>
                      <td>
                        <Tag tone={UNIT_STATUS[u.status]?.tone ?? "quiet"}>
                          {UNIT_STATUS[u.status]?.label ?? u.status}
                        </Tag>
                        {u.first_pass && <div className={styles.sub}>first pass</div>}
                      </td>
                      <td>
                        {u.status === "held" ? (
                          <>
                            {step
                              ? `${step.target ? step.target.toUpperCase() + " " : ""}${step.label}`
                              : u.step}
                            : {codeLabel(u.hold_code)}
                            <div className={styles.sub}>{OWNER[u.hold_owner ?? ""] ?? u.hold_owner}</div>
                          </>
                        ) : u.status === "in_progress" && step ? (
                          step.label
                        ) : (
                          <span className={styles.sub}>none</span>
                        )}
                      </td>
                      <td>{u.release}</td>
                      <td>{u.slot}</td>
                      <td className={ui.num}>{int(u.runs)}</td>
                      <td>{clock(u.updated_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <nav className={styles.pager} aria-label="Pages of airframes">
              <span>
                {int(page * PAGE + 1)} to {int(Math.min((page + 1) * PAGE, d.total))} of {int(d.total)}
              </span>
              <span className={styles.pagerButtons}>
                <Button disabled={page === 0} onClick={() => set({ page: page > 1 ? String(page - 1) : "" })}>
                  Previous
                </Button>
                <Button
                  disabled={(page + 1) * PAGE >= d.total}
                  onClick={() => set({ page: String(page + 1) })}
                >
                  Next
                </Button>
              </span>
            </nav>
          </>
        )}
      </QueryView>
    </>
  );
}
