/** Words and tones for what the API reports, so every screen names things the same way. */

export type Tone = "good" | "watch" | "bad" | "info" | "quiet" | "signal" | "orange";

export const MOTION = {
  move: 0.36,
  draw: 0.5,
  quick: 0.14,
  stagger: 0.025,
  ease: [0.2, 0.8, 0.2, 1] as [number, number, number, number],
} as const;

/** Live screens refresh this often (ms). */
export const LIVE_REFRESH_MS = 4000;

export const UNIT_STATUS: Record<string, { label: string; tone: Tone }> = {
  released: { label: "Released", tone: "good" },
  held: { label: "Held", tone: "bad" },
  in_progress: { label: "On the fixture", tone: "info" },
};

export const ISSUE_KIND: Record<string, { label: string; tone: Tone; means: string }> = {
  systemic: {
    label: "Systemic",
    tone: "orange",
    means: "One place fails this far more often than chance explains.",
  },
  widespread: {
    label: "Widespread",
    tone: "watch",
    means: "Fails often everywhere: the step itself, not one place.",
  },
  one_off: { label: "One-off", tone: "quiet", means: "No place stands out: handle unit by unit." },
};

export const DIMENSION: Record<string, string> = {
  slot: "Slot",
  fixture: "Fixture",
  station: "Station",
  operator: "Operator",
  release: "Release",
  fc_rev: "FC board revision",
  fc_lot: "FC board lot",
  pmu_rev: "PMU board revision",
  pmu_lot: "PMU board lot",
  orin_sku: "Module SKU",
  orin_fab: "Module FAB",
  orin_batch: "Module batch",
};

export const OWNER: Record<string, string> = {
  production: "Production",
  engineering: "Engineering",
  quality: "Quality",
  supplier: "Supplier quality",
};

export const ROLES = [
  { value: "lead", label: "Line lead" },
  { value: "operator", label: "Operator" },
  { value: "engineering", label: "Engineering" },
  { value: "quality", label: "Quality" },
] as const;

export type Role = (typeof ROLES)[number]["value"];

export const TARGET: Record<string, string> = {
  fc: "Flight controller",
  pmu: "Power module",
  orin: "Mission computer",
};

/** The recipe's steps in order, with short names for the step rail (config/recipes/standard.yaml). */
export const STEPS: { id: string; label: string; target?: string; irreversible?: boolean }[] = [
  { id: "scan_unit", label: "Scan" },
  { id: "fc_attach", label: "Attach", target: "fc" },
  { id: "fc_identify", label: "Identify", target: "fc" },
  { id: "fc_program", label: "Program", target: "fc" },
  { id: "fc_config", label: "Configure", target: "fc" },
  { id: "fc_selftest", label: "Self-test", target: "fc" },
  { id: "pmu_attach", label: "Attach", target: "pmu" },
  { id: "pmu_identify", label: "Identify", target: "pmu" },
  { id: "pmu_program", label: "Program", target: "pmu" },
  { id: "pmu_config", label: "Configure", target: "pmu" },
  { id: "pmu_selftest", label: "Self-test", target: "pmu" },
  { id: "orin_enumerate", label: "Recovery mode", target: "orin" },
  { id: "orin_identify", label: "Identify", target: "orin" },
  { id: "orin_flash", label: "Flash", target: "orin" },
  { id: "orin_verify", label: "Read back", target: "orin" },
  { id: "orin_first_boot", label: "First boot", target: "orin" },
  { id: "orin_fuse", label: "Burn fuses", target: "orin", irreversible: true },
  { id: "release_unit", label: "Release" },
];

export const STEP_INDEX: Record<string, number> = Object.fromEntries(STEPS.map((s, i) => [s.id, i]));

export const FINDING: Record<string, string> = {
  missing_step: "Not in the instruction",
  obsolete_step: "No longer done",
  order: "Out of order",
  version_drift: "Wrong version",
  missing_warning: "No warning",
};
