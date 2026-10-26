"""The station, the server and the analysis decide from what a real line can see. They never import the simulator,
never read a campaign or a run's truth; only uavtrail/evaluate.py reads truth.json."""

from __future__ import annotations

import ast
import re

from conftest import ROOT

SHIPPING = ROOT / "src" / "uavtrail"


def test_shipping_code_never_imports_the_simulator() -> None:
    for path in SHIPPING.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(n.startswith("uavsim") for n in names), path


def test_only_evaluate_reads_the_truth() -> None:
    for path in SHIPPING.rglob("*.py"):
        if path.name == "evaluate.py":
            continue
        text = path.read_text()
        assert "truth.json" not in text and "campaigns" not in text, path


def test_thresholds_live_in_config() -> None:
    for name in ("issues.py", "kpi.py"):
        text = (SHIPPING / "analysis" / name).read_text()
        assert not re.search(r"(alpha|min_failures|min_lift)\s*=\s*[0-9]", text), name


def test_every_code_a_step_raises_is_in_the_vocabulary() -> None:
    import yaml

    book = yaml.safe_load((ROOT / "config" / "codes.yaml").read_text())
    raised = set()
    for path in SHIPPING.rglob("*.py"):
        raised |= set(re.findall(r'TargetError\(\s*"([a-z_]+)"', path.read_text()))
        raised |= set(re.findall(r'RecordError\(\s*"([a-z_]+)"', path.read_text()))
    sim = (ROOT / "src" / "uavsim" / "orin_sim.py").read_text()
    raised |= set(re.findall(r'"code": "([a-z_]+)"', sim)) - {"usb_protocol", "simulator_error"}
    assert raised - set(book) == set()
