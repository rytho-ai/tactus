"""A walk through three rooms, rendered from a route: the smallest interactive work.

Each room has a two-bar loop; a route (a JSON performance) says which rooms to visit, in
order, and for how many bars. `render` returns the walk as one mix, every room's loop as its
own output for a player, and a map: bar lines, the route as spans, and each loop as a segment
a player may leave at any bar line for another room.

    tactus run route.py --out runs/walk --param-file route=walk.json
    tactus export web runs/walk --codec flac --out delivery/walk

walk.json: {"steps": [{"room": "hall", "bars": 2}, {"room": "stair", "bars": 4}]}
"""

import numpy as np

import tactus
from tactus import dsp
from tactus.timing import Clock

RATE = 48_000
CLOCK = Clock(sample_rate=RATE, tempo=96)
ROOMS = {"hall": 196.0, "stair": 246.9, "roof": 293.7}  # each room's drone, Hz
LOOP_BARS = 2


def room_loop(hz: float) -> np.ndarray:
    """Two bars of a room: a drone with a pulse on every beat, exactly LOOP_BARS long."""
    frames = CLOCK.frame(LOOP_BARS + 1)
    t = np.arange(frames) / RATE
    beat = CLOCK.frame(1, 1)
    pulse = np.exp(-(np.arange(frames) % beat) / (0.08 * RATE))
    return 0.15 * np.sin(2 * np.pi * hz * t) * (0.6 + 0.4 * pulse)


def check(route: dict) -> list[dict]:
    """The route's steps, or InvalidParameters with a message for the player."""
    steps = route.get("steps") if isinstance(route, dict) else None
    if not steps:
        raise tactus.InvalidParameters("a route needs at least one step")
    for i, step in enumerate(steps):
        if step.get("room") not in ROOMS:
            raise tactus.InvalidParameters(f"step {i}: room must be one of {sorted(ROOMS)}")
        if type(step.get("bars")) is not int or step["bars"] < 1:
            raise tactus.InvalidParameters(f"step {i}: bars must be a whole number above 0")
    return steps


def render(*, route=None):
    steps = check(route or {"steps": [{"room": "hall", "bars": 2}, {"room": "roof", "bars": 2}]})
    loops = {name: room_loop(hz) for name, hz in ROOMS.items()}
    total = sum(step["bars"] for step in steps)
    walk = np.zeros(CLOCK.frame(total + 1))
    spans, bar = [], 1
    for step in steps:
        start, end = CLOCK.frame(bar), CLOCK.frame(bar + step["bars"])
        loop = loops[step["room"]]
        walk[start:end] = np.resize(loop, end - start)  # whole loops, cut at a bar line
        spans.append({"start": start, "end": end, "label": step["room"]})
        bar += step["bars"]
    walk = dsp.fade(walk, RATE, in_s=0.01, out_s=0.2)
    loop_map = {"grid": CLOCK.grid(1, LOOP_BARS)}
    return {
        "sample_rate": RATE,
        "outputs": {"walk": walk, **loops},
        "map": {
            "outputs": {"walk": {"grid": CLOCK.grid(1, total), "lanes": {
                            "route": {"kind": "spans", "items": spans}}},
                        **{name: loop_map for name in loops}},
            "segments": {name: {"output": name, "start": 0, "end": len(loop), "loop": True,
                                "tags": ["room"],
                                "joins": [{"at": "bars", "to": {"tags": ["room"]}}]}
                         for name, loop in loops.items()},
        },
    }
