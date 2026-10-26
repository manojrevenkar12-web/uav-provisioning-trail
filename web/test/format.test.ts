import { clock, int, minutes, pct, serialTail, short } from "../src/shared/lib/format";
import { odds } from "../src/features/issues/IssuesPage";

describe("formatting", () => {
  it("writes shares, counts and durations the same way everywhere", () => {
    expect(pct(0.6125)).toBe("61.3 %");
    expect(int(1200)).toBe("1,200");
    expect(minutes(42)).toBe("42 min");
    expect(minutes(121.3)).toBe("2 h 1 min");
    expect(pct(null)).toBe("n/a");
  });

  it("shortens serials and hashes but keeps them recognisable", () => {
    expect(serialTail("HX2-26-000154")).toBe("000154");
    expect(short("0123456789abcdef", 6)).toBe("012345…");
    expect(short(null)).toBe("");
  });

  it("reads clock times in the line's own time zone", () => {
    expect(clock("2026-10-27T05:01:38+00:00")).toBe("06:01");
    expect(clock(null)).toBe("not yet");
  });

  it("turns a p-value into odds a person can weigh", () => {
    expect(odds(0.002)).toBe("1 in 500 by chance");
    expect(odds(2e-5)).toBe("1 in 50 thousand by chance");
    expect(odds(2e-7)).toBe("1 in 5.0 million by chance");
    expect(odds(1e-12)).toBe("less than 1 in a billion by chance");
    expect(odds(null)).toBe("");
  });
});
