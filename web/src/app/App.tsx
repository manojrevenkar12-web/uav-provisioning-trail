import { Route, Routes } from "react-router-dom";

import { InstructionsPage } from "../features/instructions/InstructionsPage";
import { IssuesPage } from "../features/issues/IssuesPage";
import { LinePage } from "../features/line/LinePage";
import { ReleasesPage } from "../features/releases/ReleasesPage";
import { UnitPage } from "../features/units/UnitPage";
import { UnitsPage } from "../features/units/UnitsPage";
import { EmptyState } from "../shared/ui";
import { Shell } from "./Shell";

function NotFound() {
  return (
    <EmptyState title="There is nothing at this address">
      Use the menu above, or start from the line.
    </EmptyState>
  );
}

export function AppRoutes() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<LinePage />} />
        <Route path="/issues" element={<IssuesPage />} />
        <Route path="/units" element={<UnitsPage />} />
        <Route path="/units/:unit" element={<UnitPage />} />
        <Route path="/releases" element={<ReleasesPage />} />
        <Route path="/instructions" element={<InstructionsPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Shell>
  );
}
