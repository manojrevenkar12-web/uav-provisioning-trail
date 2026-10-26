import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";

import { session } from "../src/shared/api/client";
import { fx, routes } from "./fixtures";
import { clone, json, problem, renderAt, stubApi } from "./harness";

beforeEach(() => {
  sessionStorage.clear();
  session.reset();
});

const actAs = (role: "lead" | "operator" | "engineering" | "quality", name = "Test Person") =>
  act(() => {
    session.setRole(role);
    session.setActor(name);
  });

describe("the line", () => {
  it("shows the KPIs of the shift", async () => {
    stubApi(routes());
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "The line" })).toBeInTheDocument();
    expect(screen.getByText("61.3 %")).toBeInTheDocument();
    expect(
      screen.getByText(`${fx.overview.kpis.first_pass_yield.count} of 160 airframes, no failed step`),
    ).toBeInTheDocument();
    expect(screen.getByText("Software first-pass yield")).toBeInTheDocument();
  });

  it("draws every fixture with its slots and rings the slots a systemic issue points at", async () => {
    stubApi(routes());
    renderAt("/");
    const plates = await screen.findAllByRole("region", { name: /^FX-/ });
    expect(plates).toHaveLength(3);
    const fxa = screen.getByRole("region", { name: /^FX-A/ });
    const slot3 = within(fxa).getByRole("link", { name: "Slot FX-A/3: units" });
    expect(within(slot3).getByText("Systemic")).toBeInTheDocument();
    expect(slot3).toHaveAttribute("href", "/units?slot=FX-A%2F3");
    const slot1 = within(fxa).getByRole("link", { name: "Slot FX-A/1: units" });
    expect(within(slot1).queryByText("Systemic")).not.toBeInTheDocument();
    expect(within(slot1).getByRole("img", { name: /Steps:/ })).toBeInTheDocument();
  });

  it("names failure codes in words from the server's vocabulary", async () => {
    stubApi(routes());
    renderAt("/");
    const pareto = await screen.findByRole("list", { name: "Failures by code" });
    await waitFor(() => expect(within(pareto).getByText("Module EEPROM fails its CRC")).toBeInTheDocument());
  });

  it("lists what is systemic now and what is being watched", async () => {
    stubApi(routes());
    renderAt("/");
    await screen.findByRole("heading", { name: "Systemic now" });
    expect(screen.getByRole("link", { name: /Probe cannot attach.*Slot FX-A\/3/ })).toBeInTheDocument();
    expect(screen.getByText(/of 8 modules link at USB2/)).toBeInTheDocument();
  });

  it("shows a skeleton, then says what failed and retries", async () => {
    let fail = true;
    let release: (r: Response) => void = () => {};
    stubApi({
      ...routes(),
      "GET /api/overview": () => (fail ? new Promise<Response>((r) => (release = r)) : json(fx.overview)),
    });
    renderAt("/");
    expect(await screen.findByRole("status", { name: "Loading the line" })).toBeInTheDocument();
    release(problem(503, "The traceability database is starting"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The traceability database is starting");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "The line" })).toBeInTheDocument();
  });

  it("explains an empty line", async () => {
    const o = clone(fx.overview);
    o.kpis.units.started = 0;
    stubApi({ ...routes(), "GET /api/overview": o });
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "No airframe has started yet" })).toBeInTheDocument();
  });

  it("asks for the API token and sends it from then on", async () => {
    const calls = stubApi({
      ...routes(),
      "GET /api/overview": (_u: string, init?: RequestInit) =>
        (init?.headers as Record<string, string>)["authorization"] === "Bearer s3cret"
          ? json(fx.overview)
          : problem(401, "a valid bearer token is required"),
    });
    renderAt("/");
    await userEvent.type(await screen.findByLabelText("API token"), "s3cret");
    await userEvent.click(screen.getByRole("button", { name: "Use token" }));
    expect(await screen.findByRole("heading", { level: 1, name: "The line" })).toBeInTheDocument();
    expect(calls.at(-1)!.headers["authorization"]).toBe("Bearer s3cret");
  });
});

describe("issues", () => {
  it("groups systemic, widespread and one-off issues and gives the odds", async () => {
    stubApi(routes());
    renderAt("/issues");
    const systemic = await screen.findByRole("region", { name: /^Systemic \(\d+\)/ });
    const card = within(systemic).getByRole("article", { name: "Probe cannot attach" });
    expect(within(card).getByText("FX-A/3")).toBeInTheDocument();
    expect(within(card).getByText(/by chance/)).toBeInTheDocument();
    expect(within(card).getByText(/Take the slot out of service/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /^One-off/ })).toBeInTheDocument();
  });

  it("lets an operator read issues but not act on them", async () => {
    const calls = stubApi(routes());
    actAs("operator");
    renderAt("/issues");
    const card = within(await screen.findByRole("region", { name: /^Systemic/ })).getByRole("article", {
      name: "Probe cannot attach",
    });
    await userEvent.click(within(card).getByRole("button", { name: "Act on this" }));
    expect(within(screen.getByRole("dialog")).getByText(/Operators see the issues/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("lets the lead mark an issue fixed from a given time", async () => {
    const pogo = fx.issues.issues.find((i) => i.kind === "systemic" && i.code === "link_refused")!;
    const calls = stubApi({
      ...routes(),
      [`POST /api/issues/${pogo.key}/actions`]: {
        id: 1,
        issue: pogo.key,
        action: "fixed",
        owner: "production",
        note: "pogo block replaced",
        actor: "Mia",
        effective_at: "2026-10-27T06:40:00Z",
        at: "2026-10-27T06:41:00Z",
      },
    });
    actAs("lead", "Mia");
    renderAt("/issues");
    const card = within(await screen.findByRole("region", { name: /^Systemic/ })).getByRole("article", {
      name: "Probe cannot attach",
    });
    await userEvent.click(within(card).getByRole("button", { name: "Act on this" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Mark fixed" }));
    await userEvent.type(within(dialog).getByLabelText("Fixed from"), "2026-10-27T07:40");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark fixed" }));
    expect(within(dialog).getByText("Write at least 3 characters.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("Note"), "pogo block replaced");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark fixed" }));
    expect(await within(dialog).findByText("Marked fixed by Mia.")).toBeInTheDocument();
    const body = calls.find((c) => c.method === "POST")!.body as Record<string, string>;
    expect(body.action).toBe("fixed");
    expect(body.note).toBe("pogo block replaced");
    expect(body.owner).toBe("production");
    expect(new Date(body.effective_at!).getTime()).toBe(new Date("2026-10-27T07:40").getTime());
  });
});

describe("airframes", () => {
  it("filters by slot from the address and pages through", async () => {
    const calls = stubApi(routes());
    renderAt("/units?slot=FX-A%2F3");
    expect(await screen.findByText("Every airframe that went through slot FX-A/3.")).toBeInTheDocument();
    await screen.findByRole("region", { name: "Airframes" });
    expect(calls.find((c) => c.path.startsWith("/api/units?"))!.path).toBe(
      "/api/units?slot=FX-A%2F3&limit=30&offset=0",
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(calls.at(-1)!.path).toBe("/api/units?slot=FX-A%2F3&limit=30&offset=30"));
  });

  it("says when nothing matches", async () => {
    stubApi({ ...routes(), "GET /api/units": { total: 0, rows: [] } });
    renderAt("/units?q=zzz");
    expect(await screen.findByRole("heading", { name: "No airframe matches" })).toBeInTheDocument();
  });

  it("shows a released airframe's verified trail and its certificate", async () => {
    stubApi(routes());
    const u = fx.unit.unit.unit;
    renderAt(`/units/${u}`);
    expect(await screen.findByRole("heading", { level: 1, name: u })).toBeInTheDocument();
    expect(screen.getByText(/^Trail verified: \d+ events/)).toBeInTheDocument();
    expect(await screen.findByText("1.15.0")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download certificate" })).toBeInTheDocument();
    expect(screen.getAllByText(/^ORIN Flash passed$/).length).toBeGreaterThan(0);
  });

  it("shows why a held airframe is held, and no certificate", async () => {
    stubApi(routes());
    const u = fx.held.unit.unit;
    renderAt(`/units/${u}`);
    expect(await screen.findByRole("heading", { level: 1, name: u })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Not released" })).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText(/Held at orin_identify for Supplier quality: Module EEPROM fails its CRC/),
      ).toBeInTheDocument(),
    );
  });

  it("says loudly when a trail does not verify", async () => {
    const broken = clone(fx.unit);
    broken.chain = {
      verified: false,
      problems: ["event 7 was altered after it was written"],
      events: broken.chain.events,
    };
    stubApi({ ...routes(), [`GET /api/units/${fx.unit.unit.unit}`]: broken });
    renderAt(`/units/${fx.unit.unit.unit}`);
    expect(await screen.findByText(/Trail does not verify: event 7 was altered/)).toBeInTheDocument();
  });
});

describe("releases and instructions", () => {
  it("shows each release's rollout and the recall list for a version", async () => {
    const calls = stubApi(routes());
    renderAt("/releases");
    expect(await screen.findByRole("article", { name: "R2026.10" })).toBeInTheDocument();
    expect(await screen.findByText(/released airframes carry Flight controller 1.15.0/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/where-used?target=fc&version=1.15.0")).toBe(true);
    await userEvent.click(screen.getByRole("radio", { name: "Mission computer" }));
    await waitFor(() => expect(calls.at(-1)!.path).toBe("/api/where-used?target=orin&version=3.2.0"));
  });

  it("lists where the work instruction and the release disagree", async () => {
    stubApi(routes());
    renderAt("/instructions?release=R2026.10");
    expect(
      await screen.findByText(/WI-SW-014 revision 7 against R2026.10: 4 differences/),
    ).toBeInTheDocument();
    expect(screen.getByText("WI-SW-014 says 1.14.2; R2026.10 installs 1.15.0")).toBeInTheDocument();
    expect(screen.getByText("No warning")).toBeInTheDocument();
  });

  it("says when they agree", async () => {
    stubApi({ ...routes(), "GET /api/instructions": { ...fx.instructions, findings: [] } });
    renderAt("/instructions?release=R2026.10");
    expect(await screen.findByRole("heading", { name: "The instruction matches" })).toBeInTheDocument();
  });

  it("explains an address that does not exist", async () => {
    stubApi(routes());
    renderAt("/nowhere");
    expect(
      await screen.findByRole("heading", { name: "There is nothing at this address" }),
    ).toBeInTheDocument();
  });
});
