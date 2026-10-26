/** API answers captured from the emulated line (uavsim run campaigns/dev/shift-a.yaml). */
import type {
  Certificate,
  InstructionCheck,
  Issue,
  Overview,
  Release,
  SlotState,
  UnitDetail,
  UnitRow,
  Watch,
  WhereUsed,
} from "../src/shared/api/types";
import certificate from "./fixtures/certificate.json";
import codes from "./fixtures/codes.json";
import held from "./fixtures/held.json";
import instructions from "./fixtures/instructions.json";
import issues from "./fixtures/issues.json";
import overview from "./fixtures/overview.json";
import releases from "./fixtures/releases.json";
import slots from "./fixtures/slots.json";
import unit from "./fixtures/unit.json";
import units from "./fixtures/units.json";
import whereUsed from "./fixtures/where_used.json";
import type { Routes } from "./harness";

export const fx = {
  certificate: certificate as unknown as Certificate,
  codes,
  held: held as unknown as UnitDetail,
  instructions: instructions as InstructionCheck,
  issues: issues as unknown as { issues: Issue[]; watch: Watch[] },
  overview: overview as unknown as Overview,
  releases: releases as unknown as Release[],
  slots: slots as unknown as SlotState[],
  unit: unit as unknown as UnitDetail,
  units: units as unknown as { total: number; rows: UnitRow[] },
  whereUsed: whereUsed as WhereUsed,
};

export function routes(): Routes {
  return {
    "GET /api/overview": fx.overview,
    "GET /api/slots": fx.slots,
    "GET /api/issues": fx.issues,
    "GET /api/codes": fx.codes,
    "GET /api/releases": fx.releases,
    "GET /api/units": fx.units,
    [`GET /api/units/${fx.unit.unit.unit}`]: fx.unit,
    [`GET /api/units/${fx.unit.unit.unit}/certificate`]: fx.certificate,
    [`GET /api/units/${fx.held.unit.unit}`]: fx.held,
    "GET /api/where-used": fx.whereUsed,
    "GET /api/instructions": fx.instructions,
  };
}
