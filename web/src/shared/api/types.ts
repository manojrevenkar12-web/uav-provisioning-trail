/** What the traceability server returns (src/uavtrail/server/api.py). */

export interface Problem {
  title: string;
  status: number;
  detail?: string;
}

export interface Share {
  value: number | null;
  of: number;
  count: number;
}

export interface Kpis {
  units: {
    started: number;
    released: number;
    held: number;
    in_progress: number;
    first_pass: number;
    finished: number;
    reworked: number;
  };
  first_pass_yield: Share;
  final_yield: Share;
  flash_success: Share;
  flash_first_attempt: Share;
  downtime_minutes: number;
  cycle_minutes_median: number | null;
  window: { from: string | null; to: string | null };
}

export interface Place {
  dimension: string;
  value: string;
}

export interface IssueAction {
  id: number;
  issue: string;
  action: "acknowledge" | "fixed" | "not_a_problem" | "note";
  owner: string | null;
  note: string;
  actor: string;
  effective_at: string;
  at: string;
}

export interface Effect {
  since: string;
  before: { failures: number; attempts: number; rate: number | null };
  after: { failures: number; attempts: number; rate: number | null };
  verdict: "holding" | "not holding" | "too early to tell";
}

export interface Issue {
  key: string;
  code: string;
  label: string;
  owner: string;
  kind: "systemic" | "widespread" | "one_off";
  where: Place[];
  failures: number;
  attempts: number;
  rate: number;
  rest_rate: number | null;
  p_value: number | null;
  units: number;
  first_seen: string;
  last_seen: string;
  lost_minutes: number;
  action: string;
  examples: string[];
  actions?: IssueAction[];
  effect?: Effect | null;
}

export interface Watch {
  slot: string;
  signal: string;
  share: number;
  units: number;
  interval: [number, number];
  why: string;
}

export interface Overview {
  kpis: Kpis;
  systemic: Issue[];
  one_off: number;
  watch: Watch[];
  hours: { hour: string; released: number; failures: number; flashes: number; flashes_ok: number }[];
  pareto: { code: string; failures: number; units: number; lost_minutes: string }[];
}

export interface UnitRow {
  unit: string;
  status: "released" | "held" | "in_progress";
  release: string | null;
  station: string | null;
  slot: string | null;
  step: string | null;
  hold_code: string | null;
  hold_owner: string | null;
  runs: number;
  first_pass: boolean | null;
  operator: string | null;
  dims: Record<string, string>;
  started_at: string | null;
  updated_at: string | null;
}

export interface SlotState {
  slot: string;
  station: string;
  fixture: string;
  index: number;
  current:
    | (Pick<UnitRow, "unit" | "status" | "step" | "release" | "updated_at"> & {
        slot: string;
        hold_code: string | null;
        hold_owner: string | null;
      })
    | null;
  stats: {
    slot: string;
    fixture: string;
    units: number;
    held: number;
    first_pass_yield: string | null;
    lost_minutes: string;
    top_code: string | null;
    top_code_failures: number | null;
  } | null;
  recent: { unit: string; status: string; hold_code: string | null }[];
}

export interface TrailEvent {
  seq: number;
  kind: "start" | "intent" | "result" | "recovery" | "hold";
  at: string;
  station: string;
  hash: string;
  prev: string;
  data: Record<string, unknown> & {
    step?: string;
    ok?: boolean;
    code?: string;
    seconds?: number;
    attempt?: number;
    detail?: string;
    action?: string;
    evidence?: Record<string, unknown>;
  };
}

export interface UnitDetail {
  unit: UnitRow & { certificate: Certificate | null; hold_seconds: number };
  events: TrailEvent[];
  chain: { verified: boolean; problems: string[]; events: number };
}

export interface Certificate {
  certificate: {
    unit: string;
    product: string;
    release: string;
    release_sha256: string;
    station: string;
    slot: string;
    operator: string;
    released_at: string;
    boards: Record<string, { uid: string; board_rev: string; lot: string }>;
    module: { board_id: number; sku: string; fab: string; serial: string; batch: string } | null;
    installed: Record<string, Record<string, unknown>>;
    fuses: Record<string, number> | null;
    trail_head: string;
  };
  signature: string;
  station_key: string;
}

export interface Release {
  release: string;
  product: string;
  artifacts: Record<string, string>;
  compatible: { fc: string[]; pmu: string[]; orin: { board_id: number; sku: string[]; fab: string[] } };
  units: { released?: number; held?: number; units?: number };
}

export interface WhereUsed {
  target: string;
  version: string;
  units: { unit: string; release: string; slot: string; released_at: string }[];
}

export interface Finding {
  kind: "missing_step" | "obsolete_step" | "order" | "version_drift" | "missing_warning";
  step: string;
  detail: string;
}

export interface InstructionCheck {
  document: string;
  revision: number;
  release: string;
  findings: Finding[];
}
