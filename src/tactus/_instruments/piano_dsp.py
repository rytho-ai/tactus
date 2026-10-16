"""Numeric primitives adapted from DAWG (MIT); see LICENSE.dawg and NOTICE.md."""

import math

import numpy as np
from numba import njit
from scipy.signal import lfilter

TAU = 2 * math.pi
LN1000 = math.log(1000)


def jsround(x):
    return math.floor(x + 0.5)


def seed_hash(text):
    value = 0x811C9DC5
    # JS hashes UTF-16 code units, including surrogate pairs.
    raw = text.encode("utf-16-le", errors="surrogatepass")
    for i in range(0, len(raw), 2):
        value = ((value ^ (raw[i] | raw[i + 1] << 8)) * 0x01000193) & 0xFFFFFFFF
    return value


def random_stream(seed):
    state = seed_hash(seed)
    while True:
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        value = ((state ^ (state >> 15)) * (1 | state)) & 0xFFFFFFFF
        value = (
            (value + (((value ^ (value >> 7)) * (61 | value)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        ) ^ value
        yield ((value ^ (value >> 14)) & 0xFFFFFFFF) / 4294967296


def hammer_pulse(length, sharp):
    pulse = np.array([math.sin(math.pi * (m + 0.5) / length) ** sharp for m in range(length)])
    return pulse / sum(pulse)


def pulse_mag(pulse, angle):
    re = im = 0.0
    for m, value in enumerate(pulse):
        re += value * math.cos(angle * m)
        im -= value * math.sin(angle * m)
    return math.hypot(re, im)


def biquad(kind, hz, q, db, rate):
    """RBJ coefficients in the upstream arithmetic order."""
    w = TAU * min(max(hz, 10), rate * 0.45) / rate
    cw, sw = math.cos(w), math.sin(w)
    alpha, amp = sw / (2 * q), 10 ** (db / 40)
    if kind == "bpf":
        b0, b1, b2, a0, a1, a2 = alpha, 0, -alpha, 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "peak":
        b0, b1, b2 = 1 + alpha * amp, -2 * cw, 1 - alpha * amp
        a0, a1, a2 = 1 + alpha / amp, -2 * cw, 1 - alpha / amp
    else:
        s = 2 * math.sqrt(amp) * alpha
        if kind == "lowshelf":
            b0 = amp * (amp + 1 - (amp - 1) * cw + s)
            b1 = 2 * amp * (amp - 1 - (amp + 1) * cw)
            b2 = amp * (amp + 1 - (amp - 1) * cw - s)
            a0 = amp + 1 + (amp - 1) * cw + s
            a1 = -2 * (amp - 1 + (amp + 1) * cw)
            a2 = amp + 1 + (amp - 1) * cw - s
        elif kind == "highshelf":
            b0 = amp * (amp + 1 + (amp - 1) * cw + s)
            b1 = -2 * amp * (amp - 1 + (amp + 1) * cw)
            b2 = amp * (amp + 1 + (amp - 1) * cw - s)
            a0 = amp + 1 - (amp - 1) * cw + s
            a1 = 2 * (amp - 1 - (amp + 1) * cw)
            a2 = amp + 1 - (amp - 1) * cw - s
        else:
            raise ValueError(f"Unsupported biquad {kind}")
    return np.array([b0 / a0, b1 / a0, b2 / a0]), np.array([1, a1 / a0, a2 / a0])


class Burst:
    """Stateful seeded band-pass noise burst, added in control-block order."""

    def __init__(self, seed, hz, q, tau, gain, rate):
        self.random = random_stream(seed)
        self.b, self.a = biquad("bpf", hz, q, 0, rate)
        self.z1 = self.z2 = 0.0
        self.n = 0
        self.attack = max(1, jsround(0.0005 * rate))
        self.k = math.exp(-1 / (tau * rate))
        self.length = self.attack + math.ceil(tau * 7 * rate)
        self.env, self.gain = 1.0, gain

    def next(self):
        i = self.n
        self.n += 1
        if i >= self.length:
            return 0.0
        if i < self.attack:
            env = i / self.attack
        else:
            self.env *= self.k
            env = self.env
        x = next(self.random) * 2 - 1
        y = self.b[0] * x + self.z1
        z1 = self.b[1] * x - self.a[1] * y + self.z2
        z2 = self.b[2] * x - self.a[2] * y
        self.z1 = 0.0 if abs(z1) < 1e-30 else z1
        self.z2 = 0.0 if abs(z2) < 1e-30 else z2
        return y * env * self.gain


@njit(cache=True, fastmath=False)
def run_modes(re, im, cr, ci, u, g, pulse, position, count, n):
    """Reference recurrence; kept callable without acceleration for verification."""
    out = np.zeros(count)
    for s in range(count):
        x = pulse[position + s] if position + s < len(pulse) else 0.0
        acc = 0.0
        for k in range(n):
            a, b = re[k], im[k]
            nr = cr[k] * a - ci[k] * b
            if x != 0:
                nr += u[k] * x
            ni = ci[k] * a + cr[k] * b
            re[k], im[k] = nr, ni
            acc += g[k] * ni
        out[s] = acc
    return out


class ModeBank:
    def __init__(self, modes, rate):
        self.n = len(modes)
        self.w = np.array([TAU * hz / rate for hz, _, _ in modes])
        self.r = np.array([math.exp(-LN1000 / (max(1e-4, t60) * rate)) for _, t60, _ in modes])
        self.u = np.array([gain for _, _, gain in modes])
        self.g = np.ones(self.n)
        self.g0 = self.g.copy()
        self.re, self.im = np.zeros(self.n), np.zeros(self.n)
        self.ratio = 1.0
        self.set_angles()

    def set_angles(self):
        angle = self.w * self.ratio
        muted = angle >= TAU * 0.45
        self.g = np.where(muted, 0, self.g0)
        angle = np.where(muted, self.w, angle)
        self.cr = np.array([r * math.cos(a) for r, a in zip(self.r, angle)])
        self.ci = np.array([r * math.sin(a) for r, a in zip(self.r, angle)])

    def damp(self, t60s, rate):
        for k in range(self.n):
            r = math.exp(-LN1000 / (max(1e-4, t60s[k]) * rate))
            self.r[k] = min(self.r[k], r)
        self.set_angles()

    def run(self, pulse, position, count):
        return run_modes(
            self.re, self.im, self.cr, self.ci, self.u, self.g, pulse, position, count, self.n
        )

    def cull(self):
        k = 0
        while k < self.n:
            if math.hypot(self.re[k], self.im[k]) * abs(self.g0[k]) < 2e-6:
                self.n -= 1
                for arr in (
                    self.re,
                    self.im,
                    self.cr,
                    self.ci,
                    self.w,
                    self.r,
                    self.u,
                    self.g,
                    self.g0,
                ):
                    arr[k] = arr[self.n]
            else:
                k += 1


def body_eq(audio, family, rate):
    settings = {
        "grand": [
            ("lowshelf", 120, 0.7, 1.5),
            ("peak", 250, 0.8, 2),
            ("peak", 2500, 1, -2),
            ("highshelf", 6000, 0.7, -2),
        ],
        "felt": [("lowshelf", 150, 0.7, 2), ("peak", 400, 0.9, 1.5), ("highshelf", 2500, 0.7, -7)],
    }
    for kind, hz, q, db in settings[family]:
        b, a = biquad(kind, hz, q, db, rate)
        audio = lfilter(b, a, audio, axis=0)
    return audio
