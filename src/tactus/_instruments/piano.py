"""Grand/felt acoustic PianoVoice port from DAWG, MIT. No samples or TS runtime.

Voice accepts resolved frequency/velocity and explicit note seed. It owns mutable
state for one strike; process blocks retain it, note_off/damp change future decay.
Prepared strings and DAWG calibration trims are outside this first port.
"""

import math
from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np

from .piano_dsp import (
    LN1000,
    TAU,
    Burst,
    ModeBank,
    hammer_pulse,
    jsround,
    pulse_mag,
    random_stream,
)


def clamp(x, low, high):
    return min(max(x, low), high)


@dataclass(frozen=True)
class PianoParams:
    hardness: float = 0.5
    touch: float = 1
    inharm: float = 1
    unison: float = 0.7
    decay: float = 1
    release: float = 1
    strike: float = 0.12
    after: float = 0.3
    knock: float = 0.5
    noise: float = 0.25
    felt: float = 0
    width: float = 0.6
    stretch: float = 1

    def __post_init__(self):
        for name, value in vars(self).items():
            bounds = (0, 1)
            if name == "inharm":
                bounds = (0, 4)
            elif name == "unison":
                bounds = (0, 30)
            elif name in ("decay", "release"):
                bounds = (0.1, 4)
            elif name == "strike":
                bounds = (0.04, 0.3)
            if not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
                raise ValueError(f"Invalid {name}: {value}")


def params_for(family="grand", **overrides):
    if family not in ("grand", "felt"):
        raise ValueError("Supported piano families: grand, felt")
    base = PianoParams() if family == "grand" else PianoParams(felt=1, hardness=0.3, noise=0.6)
    return replace(base, **overrides)


def piano_b(key, mult):
    key = clamp(key, 21, 108)
    lg = -4 + (key - 33) / 75 * 2.3 if key >= 33 else -4 + (33 - key) / 12 * 0.45
    return mult * 10**lg


def octave_widening(low, inharm):
    bl, bu = piano_b(low, inharm), piano_b(low + 12, inharm)
    c21 = 600 * math.log2((1 + 4 * bl) / (1 + bl))
    c42 = 600 * math.log2(((1 + 16 * bl) * (1 + bu)) / ((1 + bl) * (1 + 4 * bu)))
    w42 = 0.5 * clamp((72 - (low + 12)) / 12, 0, 1)
    return (1 - w42) * c21 + w42 * c42


@lru_cache(maxsize=32)
def stretch_table(inharm):
    table = np.zeros(128)
    for p in range(75, 128):
        table[p] = table[p - 12] + octave_widening(p - 12, inharm)
    for p in range(62, -1, -1):
        table[p] = table[p + 12] - octave_widening(p, inharm)
    table.flags.writeable = False
    return table


def piano_f1(hz, p):
    if p.stretch <= 0:
        return hz
    key = clamp(69 + 12 * math.log2(hz / 440), 0, 127)
    low, high = math.floor(key), min(127, math.floor(key) + 1)
    table = stretch_table(p.inharm)
    cents = table[low] + (table[high] - table[low]) * (key - low)
    return hz * 2 ** (p.stretch * cents / 1200)


class PianoVoice:
    def __init__(self, hz, velocity, seed, params, rate, *, soft=0):
        if (
            not math.isfinite(hz)
            or hz <= 0
            or not math.isfinite(velocity)
            or not 0 <= velocity <= 1
        ):
            raise ValueError("Positive finite Hz and velocity in [0, 1] required")
        if (
            not isinstance(rate, int)
            or rate < 8000
            or not math.isfinite(soft)
            or not 0 <= soft <= 1
        ):
            raise ValueError("Integer rate >= 8000 and soft in [0, 1] required")
        self.rate, self.p, self.seed = rate, params, seed
        self.pos = self.age = 0
        self.released = False
        self.bursts = []
        v = clamp(0.8 + (velocity - 0.8) * params.touch, 0.01, 1)
        key = 69 + 12 * math.log2(hz / 440)
        near = jsround(key)
        key = clamp(near if abs(key - near) < 1e-6 else key, 21, 108)
        self.key = key
        key_pos = (key - 21) / 87
        random = random_stream(seed + ":piano")
        b = piano_b(key, params.inharm)
        f1 = piano_f1(hz, params)
        f0 = f1 / math.sqrt(1 + b)
        t1 = 28 * 2 ** (-(clamp(key, 21, 108) - 21) / 22) * params.decay * (1 - 0.15 * params.felt)
        after = clamp(params.after, 0, 0.95)
        th_ms = (
            (3.5 + (0.8 - 3.5) * key_pos)
            * (1.6 + (0.7 - 1.6) * v)
            * (1 + 1.5 * params.felt)
            * (1.3 - 0.6 * params.hardness)
        )
        soft_fc = 35 * 2 ** (5 * v * (0.4 + 0.6 * params.hardness) + 1.5 * key_pos) * 0.75**soft
        soft_floor = 1 - 0.75 * soft
        if soft > 0:
            after = clamp(after + (1 - after) * 0.4 * soft, 0, 0.95)
        self.pulse = hammer_pulse(max(2, jsround(th_ms * 1e-3 * rate)), 1 + 2 * v * params.hardness)
        strings = 1 if key < 31 else 2 if key < 42 else 3
        spread = (
            0.08
            if strings == 1
            else params.unison * (1 - soft / strings)
            if soft > 0
            else params.unison
        )
        partials = 0
        while partials < 160:
            n = partials + 1
            if n * f0 * math.sqrt(1 + b * n * n) >= 0.45 * rate:
                break
            partials = n
        candidates = []
        energy = sum0 = sum_w = 0.0
        for n in range(1, partials + 1):
            fn = n * f0 * math.sqrt(1 + b * n * n)
            shape = math.sin(n * math.pi * params.strike)
            if abs(shape) < 1e-3:
                continue
            tn = 1 / (1 / t1 + (fn / 3000) ** 2 / (1.2 * params.decay))
            energy += shape * shape
            weight = (
                max(soft_floor, ((1 + (f1 / soft_fc) ** 2) / (1 + (fn / soft_fc) ** 2)) ** soft)
                if soft > 0
                else 1
            )
            u = shape * weight
            sum0 += abs(shape)
            sum_w += abs(u)
            if n <= 12:
                d = spread / 2 * (1 + 0.3 * (next(random) - 0.5))
                candidates.extend(
                    [
                        (fn, tn * 0.3, u * (1 - after)),
                        (fn * 2 ** (-d / 1200), tn, u * after / 2),
                        (fn * 2 ** (d / 1200), tn, u * after / 2),
                    ]
                )
            else:
                candidates.append((fn, tn * 0.6, u))
        loud = v**1.4 * (1 - 0.4 * params.felt)
        if soft > 0:
            loud *= (1 - 0.3 * soft) * math.sqrt(sum0 / max(sum_w, 1e-9))
        gain = 0.35 * loud / math.sqrt(max(energy, 1e-9))
        mags = [pulse_mag(self.pulse, TAU * hz / rate) * abs(u) for hz, _, u in candidates]
        peak = max([0, *mags])
        modes = [
            (hz, t60, u * gain)
            for (hz, t60, u), mag in zip(candidates, mags)
            if mag >= peak * 1e-4 and 0 < hz < 0.45 * rate
        ]
        self.bank = ModeBank(modes, rate)
        pan = params.width * clamp((key - 64) / 44, -1, 1) * 0.8
        angle = (clamp(pan, -1, 1) + 1) * math.pi / 4
        self.gl, self.gr = math.cos(angle), math.sin(angle)
        if params.knock > 0:
            self.bursts.extend(
                [
                    Burst(
                        seed + ":knock",
                        90 + 160 * key_pos,
                        1,
                        0.02 + 0.03 * (1 - key_pos),
                        params.knock * 0.05 * v**1.5,
                        rate,
                    ),
                    Burst(
                        seed + ":click",
                        2800,
                        1.5,
                        0.002,
                        0.02 * v * v * params.hardness * (1 - params.felt) * (1 - 0.3 * soft),
                        rate,
                    ),
                ]
            )
        if params.felt > 0 and params.noise > 0:
            self.bursts.append(
                Burst(seed + ":thud", 300, 0.9, 0.03, 0.04 * params.felt * params.noise * v, rate)
            )

    def note_off(self):
        if self.released:
            return
        self.released = True
        if jsround(self.key) >= 89:
            return
        base = self.p.release * (0.12 + 0.55 * clamp((64 - self.key) / 43, 0, 1))
        self.bank.damp([base / (1 + w * self.rate / TAU / 2000) for w in self.bank.w], self.rate)
        if self.p.noise > 0:
            self.bursts.append(
                Burst(self.seed + ":keyoff", 500, 1.2, 0.015, 0.012 * self.p.noise, self.rate)
            )

    def damp(self, tau):
        self.bank.damp(np.full(len(self.bank.w), LN1000 * tau), self.rate)

    def set_cents(self, cents):
        ratio = 2 ** (cents / 1200)
        if ratio != self.bank.ratio:
            self.bank.ratio = ratio
            self.bank.set_angles()

    def process(self, count):
        if not isinstance(count, int) or count < 0:
            raise ValueError("Nonnegative integer count required")
        if count == 0:
            return np.zeros(0)
        tmp = self.bank.run(self.pulse, self.pos, count)
        self.pos += min(count, max(0, len(self.pulse) - self.pos))
        for burst in self.bursts:
            if burst.n < burst.length:
                for i in range(count):
                    tmp[i] += burst.next()
        self.age += count
        if self.age % 256 < count:
            self.bank.cull()
        return tmp

    @property
    def alive(self):
        return self.bank.n > 0 or any(b.n < b.length for b in self.bursts)
