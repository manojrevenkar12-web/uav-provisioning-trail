"""The fuse burn runs only when nothing is unmet; every precondition alone is enough to stop it."""

from __future__ import annotations

import itertools

from uavtrail.station.guards import REQUIRED_STEPS, FuseContext, already_done, unmet

FUSES = {"secure_boot": 1, "odm_production_mode": 1}


def ready() -> FuseContext:
    return FuseContext(FUSES, "production", set(REQUIRED_STEPS), True, {}, True)


def test_a_ready_module_may_be_burnt() -> None:
    assert unmet(ready()) == []


def test_each_precondition_alone_stops_the_burn() -> None:
    breakers = {
        "release": lambda c: setattr(c, "release_fuses", {}),
        "mode": lambda c: setattr(c, "mode", "engineering"),
        "steps": lambda c: c.passed_this_run.discard("orin_verify"),
        "module": lambda c: setattr(c, "module_supported", False),
        "unread": lambda c: setattr(c, "current_fuses", None),
        "other": lambda c: setattr(c, "current_fuses", {"secure_boot": 0}),
        "trail": lambda c: setattr(c, "trail_persisted", False),
    }
    for name, breaker in breakers.items():
        c = ready()
        breaker(c)
        assert unmet(c), name


def test_every_combination_of_failures_is_refused() -> None:
    switches = list(itertools.product([True, False], repeat=5))
    for mode_ok, steps_ok, module_ok, trail_ok, fuses_known in switches:
        c = FuseContext(
            FUSES,
            "production" if mode_ok else "test",
            set(REQUIRED_STEPS) if steps_ok else set(),
            module_ok,
            {} if fuses_known else None,
            trail_ok,
        )
        allowed = not unmet(c)
        assert allowed == all((mode_ok, steps_ok, module_ok, trail_ok, fuses_known))


def test_a_module_already_burnt_as_released_is_not_burnt_again() -> None:
    c = ready()
    c.current_fuses = dict(FUSES)
    assert already_done(c)
