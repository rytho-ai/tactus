"""DAWG MIT bowed-waveguide tuning, loss and interpolation primitives."""

import math

import numpy as np
from numba import njit

from .bow_tables import BETA_SAFE, WINDOW_HI, WINDOW_LO


@njit(cache=True)
def clamp(x, lo, hi):
    return lo if x < lo else min(x, hi)


@njit(cache=True)
def jsround(x):
    return math.floor(x + 0.5)


@njit(cache=True)
def one_pole_delay(p, w):
    if w < 1e-9:
        return p / (1 - p)
    return math.atan2(p * math.sin(w), 1 - p * math.cos(w)) / w


@njit(cache=True)
def design_loss(f0, t0, fh, th, sr):
    w0 = 2 * math.pi * f0 / sr
    wh = 2 * math.pi * min(fh, 0.45 * sr) / sr
    g0 = 0.001 ** (1 / (t0 * f0))
    gh = 0.001 ** (1 / (th * f0))
    want = gh / g0
    lo, hi = 0.0, 0.95
    if wh <= w0 or want >= 1:
        hi = 0.0
    for _ in range(50):
        if hi <= 0:
            break
        mid = (lo + hi) / 2
        ratio = math.sqrt(
            (1 - 2 * mid * math.cos(w0) + mid * mid) / (1 - 2 * mid * math.cos(wh) + mid * mid)
        )
        if ratio > want:
            lo = mid
        else:
            hi = mid
    p = (lo + hi) / 2
    g = g0 * math.sqrt(1 - 2 * p * math.cos(w0) + p * p) / (1 - p)
    if g > 0.99995:
        a, b = 0.0, p
        for _ in range(50):
            mid = (a + b) / 2
            gm = g0 * math.sqrt(1 - 2 * mid * math.cos(w0) + mid * mid) / (1 - mid)
            if gm > 0.99995:
                b = mid
            else:
                a = mid
        p = a
    g = min(0.99995, g0 * math.sqrt(1 - 2 * p * math.cos(w0) + p * p) / (1 - p))
    return g, p


@njit(cache=True)
def allpass_delay(a, w):
    if w < 1e-9:
        return (1 - a) / (1 + a)
    s, c = math.sin(w), math.cos(w)
    phase = math.atan2(-s, a + c) - math.atan2(-a * s, 1 + a * c)
    while phase > 0:
        phase -= 2 * math.pi
    while phase <= -2 * math.pi:
        phase += 2 * math.pi
    return -phase / w


@njit(cache=True)
def thiran_for(d, w):
    a = (1 - d) / (1 + d)
    if w < 1e-9:
        return a
    s, c = math.sin(w), math.cos(w)
    for _ in range(4):
        f = allpass_delay(a, w) - d
        if abs(f) < 1e-10:
            break
        p, q = a + c, 1 + a * c
        df = -(s / (p * p + s * s) + s / (q * q + a * a * s * s)) / w
        if df == 0:
            break
        a = clamp(a - f / df, -0.9, 0.9)
    return a


@njit(cache=True)
def playable_beta(pos, period, t60):
    floor = min(0.4, 4 / max(1, period))
    want = clamp(pos, max(0.08, floor), 0.4)
    y = int(clamp(math.floor((math.log2(max(1, period)) - 5) / 0.25), 0, len(BETA_SAFE) - 1))
    x = 0
    thresholds = (0.4, 0.6, 1.0, 1.5, 2.2, 3.2, 4.5)
    while x < 5 and t60 >= thresholds[x + 1]:
        x += 1
    raw = BETA_SAFE[y, x]
    inner = raw & (raw << 1) & (raw >> 1)
    mask = inner if inner else raw
    best, gap = want, math.inf
    for k in range(17):
        if not mask & (1 << k):
            continue
        beta = 0.08 + 0.02 * k
        if beta < floor - 1e-9:
            continue
        d = abs(beta - want)
        if d < gap - 1e-9:
            gap, best = d, beta
    return best


@njit(cache=True)
def schelleng_slope(pressure, beta, v, period):
    lp = math.log2(max(1, period))
    y = int(clamp(math.floor((lp - 4.5) / 0.25), 0, len(WINDOW_LO) - 1))
    x = int(clamp(math.floor((beta - 0.08 + 1e-9) / 0.02), 0, WINDOW_LO.shape[1] - 1))
    lo, hi = WINDOW_LO[y, x], min(WINDOW_HI[y, x], WINDOW_LO[y, x] + 10)
    a, b = lo + 3, hi - 3
    step = a + (b - a) * clamp(pressure, 0, 1) if b > a else (lo + hi) / 2
    r = 0.01 * 2 ** (step / 4)
    return 0.25 / (r * max(1e-6, v))


def unit(seed, index, slot):
    def fmix(h):
        h ^= h >> 16
        h = h * 0x85EBCA6B & 0xFFFFFFFF
        h ^= h >> 13
        h = h * 0xC2B2AE35 & 0xFFFFFFFF
        h ^= h >> 16
        return h & 0xFFFFFFFF

    a = fmix((seed ^ ((index * 0x9E3779B1) & 0xFFFFFFFF)) & 0xFFFFFFFF)
    return fmix(a ^ (((slot + 1) * 0x7FEB352D) & 0xFFFFFFFF)) / 4294967296


def halfband_taps():
    def i0(x):
        total = term = 1.0
        for k in range(1, 50):
            term *= (x / (2 * k)) ** 2
            total += term
            if term < 1e-12 * total:
                break
        return total

    taps, offsets = [], []
    for n in range(47):
        k = n - 23
        sinc = 0.5 if k == 0 else math.sin(math.pi * k / 2) / (math.pi * k)
        w = i0(8 * math.sqrt(max(0, 1 - (k / 23) ** 2))) / i0(8)
        value = 0.0 if k != 0 and k % 2 == 0 else sinc * w
        if value != 0:
            taps.append(value)
            offsets.append(n)
    return np.array(taps), np.array(offsets, dtype=np.int64)


@njit(cache=True)
def interpolate(points, t, column, default):
    if len(points) == 0:
        return default
    if t <= points[0, 0]:
        return points[0, column]
    for i in range(1, len(points)):
        if t < points[i, 0]:
            fraction = (t - points[i - 1, 0]) / (points[i, 0] - points[i - 1, 0])
            return points[i - 1, column] + (points[i, column] - points[i - 1, column]) * fraction
    return points[-1, column]
