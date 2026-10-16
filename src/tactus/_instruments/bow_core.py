"""Stateful DAWG BowedString port, MIT. Explicit waveguide and controller state.

The Python class is the readable reference. Its methods share the same arithmetic
with the compiled class selected by bow.py after profiling. No Python callbacks
enter the sample loop: explicit piecewise-linear control/pitch arrays do instead.
"""

import math

import numpy as np

from .bow_math import (
    clamp,
    design_loss,
    interpolate,
    jsround,
    one_pole_delay,
    playable_beta,
    schelleng_slope,
    thiran_for,
)


class BowCore:
    def __init__(
        self,
        spec,
        hz,
        velocity,
        hold,
        sr,
        max_seconds,
        trem_rate,
        trem_phase,
        taps,
        offsets,
        controls,
        cents,
        vib_hz,
        vib_depth,
    ):
        self.spec = spec
        self.f0 = float(hz)
        self.hz = float(hz)
        self.from_hz = float(hz)
        self.sr = float(sr)
        self.os = 2 if sr / hz < 24 else 1
        self.rate = float(sr * self.os)
        self.max_seconds = float(max_seconds)
        self.velocity = float(velocity)
        self.trem_rate = float(trem_rate)
        self.trem_phase = float(trem_phase)
        self.vib_hz = float(vib_hz)
        self.vib_depth = float(vib_depth)
        self.controls = controls
        self.cents = cents
        self.sg, self.sp = self.loss(hz)
        size = 16
        while size < self.rate / hz * 4.5 + 16:
            size <<= 1
        self.nb = np.zeros(size)
        self.bb = np.zeros(size)
        self.mask = size - 1
        self.nw = self.bw = 0
        self.Nn = self.Nb = 1
        self.a = self.tx1 = self.ty1 = self.sy = 0.0
        self.beta = playable_beta(spec[3], self.rate / hz, self.t60(hz))
        self.from_beta = self.to_beta = 0.0
        self.slur_g = self.slur_p = 0.0
        self.slur_loss = False
        self.slur_at = -1
        self.slur_len = 1
        self.cents_at = 0
        self.steady = True
        self.stroke_err = 0.0
        self.stroke_count = self.stroke_skip = 0
        self.n = 0
        self.off = jsround(hold * self.rate)
        self.quiet = 0
        self.slope = 3.0
        self.vtarget = 0.1
        self.gain = self.tone_a = 1.0
        self.tone_y = 0.0
        self.lock = 0.0
        self.target = 1.0
        self.bp_b = self.bp_a1 = self.bp_a2 = 0.0
        self.bp_x1 = self.bp_x2 = self.bp_y1 = self.bp_y2 = 0.0
        self.last_cross = -1.0
        self.dc_r = 1 - 2 * math.pi * 10 / sr
        self.dc_x = self.dc_y = 0.0
        self.done = False
        self.taps, self.offsets = taps, offsets
        self.history = np.zeros(64)
        self.write = 0
        self.control(0.0)
        self.retune(hz, True)

    def t60(self, hz):
        return self.spec[0] * (hz / 261.6255653005986) ** -self.spec[1]

    def loss(self, hz):
        t0 = self.t60(hz)
        damp = clamp(self.spec[2] + (1 - self.spec[2]) * 0.5 * self.spec[10], 0.0, 1.0)
        return design_loss(hz, t0, max(3000.0, 2 * hz), t0 / (1 + 99 * damp * damp), self.rate)

    def can_slur_to(self, hz):
        semis = abs(12 * math.log2(hz / self.f0))
        os = 2 if self.sr / hz < 24 else 1
        return semis <= 24 and os == self.os

    def release_at(self, at):
        n = at * self.os
        if n < self.off:
            self.off = max(self.n, n)

    def slur_to(self, hz, at, hold, cents):
        n = max(self.n, at * self.os)
        self.from_hz = self.current_hz()
        self.hz = hz
        self.slur_at = n
        self.slur_len = max(1, jsround(0.007 * self.rate))
        self.off = n + jsround(hold * self.rate)
        self.cents = cents
        self.cents_at = n
        self.from_beta = self.beta
        self.to_beta = playable_beta(self.spec[3], self.rate / hz, self.t60(hz))
        self.slur_g, self.slur_p = self.loss(hz)
        self.slur_loss = True

    def current_hz(self):
        if self.slur_at < 0 or self.n >= self.slur_at + self.slur_len:
            return self.hz
        if self.n < self.slur_at:
            return self.from_hz
        k = (self.n - self.slur_at) / self.slur_len
        return self.from_hz * (self.hz / self.from_hz) ** k

    def retune(self, hz, first):
        w0 = 2 * math.pi * hz / self.rate
        total = self.rate / hz * (1 + self.lock) - one_pole_delay(self.sp, w0)
        self.target = self.rate / hz
        alpha = math.sin(w0) / 6
        a0 = 1 + alpha
        self.bp_b = alpha / a0
        self.bp_a1 = -2 * math.cos(w0) / a0
        self.bp_a2 = (1 - alpha) / a0
        if first:
            self.beta = playable_beta(self.spec[3], total, self.t60(hz))
            self.Nb = max(1, jsround(self.beta * total))
        elif self.slur_at >= 0 and self.n >= self.slur_at:
            if self.slur_loss:
                self.sg, self.sp = self.slur_g, self.slur_p
                self.slur_loss = False
                self.lock = 0.0
            k = min(1.0, (self.n - self.slur_at) / self.slur_len)
            self.beta = self.from_beta + (self.to_beta - self.from_beta) * k
            self.Nb = max(1, jsround(self.beta * total))
        rest = total - self.Nb
        nn = max(1, math.floor(rest - 0.5))
        d = clamp(rest - nn, 0.5, 1.5)
        a = thiran_for(d, w0)
        if not first and nn != self.Nn:
            self.tx1 = self.nb[(self.nw - 1 - nn) & self.mask]
            pos = self.nw - 1 - nn - d
            i0 = math.floor(pos)
            fraction = pos - i0
            self.ty1 = (
                self.nb[i0 & self.mask] * (1 - fraction) + self.nb[(i0 + 1) & self.mask] * fraction
            )
        self.Nn, self.a = nn, a

    def control(self, t):
        pressure = interpolate(self.controls, t, 1, self.spec[4])
        speed = interpolate(self.controls, t, 2, self.spec[5])
        sord = clamp(interpolate(self.controls, t, 3, self.spec[10]), 0.0, 1.0)
        dyn = interpolate(self.controls, t, 4, 1.0)
        d = clamp(self.velocity * dyn, 0.0, 1.0)
        v = (0.05 + 0.25 * clamp(speed, 0.0, 1.0)) * 8 ** (d - 1) * 0.9 + 0.005
        self.vtarget = v
        self.slope = schelleng_slope(pressure, self.beta, v, self.rate / self.hz)
        self.gain = (
            1.6
            * (self.beta / 0.12)
            * 10 ** (-10 * (1 - d) / 20)
            * min(1.0, d / 0.05)
            * (1 - 0.45 * sord)
        )
        fc = min(
            0.45 * self.sr,
            1400
            * 2 ** (3 * d)
            * (0.6 + 0.8 * clamp(pressure, 0.0, 1.0))
            * math.sqrt(0.12 / self.beta)
            * (1 - 0.7 * sord),
        )
        self.tone_a = 1 - math.exp(-2 * math.pi * fc / self.sr)

    def tick(self, attack, lift):
        n = self.n
        on = n < self.off
        env = min(1.0, (n + 1) / attack) if on else max(0.0, 1 - (n - self.off) / lift)
        direction = 1.0
        if self.trem_rate > 0:
            s = math.sin(math.pi * (self.trem_rate * (n / self.rate) + self.trem_phase))
            direction = math.tanh(4 * s)
            steady = abs(s) > 0.7
            if steady != self.steady:
                if self.steady and self.stroke_count > 0:
                    self.lock = clamp(
                        self.lock - 0.2 * self.stroke_err / self.stroke_count, -0.03, 0.03
                    )
                self.steady = steady
                self.stroke_err = 0.0
                self.stroke_count = self.stroke_skip = 0
        bow_vel = self.vtarget * (env if on else 1) * direction
        contact = 1.0 if on or env > 0 else 0.0
        slope = self.slope if on else self.slope / max(1e-3, env * env)
        if self.trem_rate > 0:
            slope /= max(0.05, abs(direction)) ** 2
        b_out = self.bb[(self.bw - self.Nb) & self.mask]
        raw = self.nb[(self.nw - self.Nn) & self.mask]
        n_out = self.a * raw + self.tx1 - self.a * self.ty1
        self.tx1, self.ty1 = raw, n_out
        self.sy = self.sg * (1 - self.sp) * b_out + self.sp * self.sy
        bridge_refl, nut_refl = -self.sy, -n_out
        dv = bow_vel - (bridge_refl + nut_refl)
        r = 1 / (abs(dv * slope) + 0.75)
        r2 = r * r
        f = min(1.0, r2 * r2)
        nv = contact * dv * f
        self.nb[self.nw & self.mask] = bridge_refl + nv
        self.bb[self.bw & self.mask] = nut_refl + nv
        self.nw += 1
        self.bw += 1
        if on:
            self.track(b_out, n)
        self.n += 1
        return b_out

    def track(self, x, n):
        y = self.bp_b * (x - self.bp_x2) - self.bp_a1 * self.bp_y1 - self.bp_a2 * self.bp_y2
        self.bp_x2, self.bp_x1 = self.bp_x1, x
        prev = self.bp_y1
        self.bp_y2, self.bp_y1 = prev, y
        if not (prev < 0 and y >= 0):
            return
        cross = n - 1 + prev / (prev - y)
        last = self.last_cross if self.steady else -1.0
        self.last_cross = cross if self.steady else -1.0
        if last < 0 or n < 0.05 * self.rate:
            return
        if self.slur_at >= 0 and n < self.slur_at + self.slur_len + 0.02 * self.rate:
            return
        period = cross - last
        err = period / self.target - 1
        if abs(err) > 0.1:
            return
        if self.trem_rate > 0:
            self.stroke_skip += 1
            if self.stroke_skip > 1:
                self.stroke_err += err
                self.stroke_count += 1
            return
        self.lock = clamp(self.lock - 0.25 * err, -0.03, 0.03)

    def decimate(self, a, b):
        self.history[self.write] = a
        newest = self.write
        self.write = (self.write + 1) & 63
        self.history[self.write] = b
        self.write = (self.write + 1) & 63
        acc = 0.0
        for i in range(len(self.taps)):
            acc += self.taps[i] * self.history[(newest - self.offsets[i]) & 63]
        return acc

    def process(self, count):
        out = np.zeros(count)
        if self.done:
            return out
        attack = max(1.0, self.spec[6] * self.rate)
        lift = max(1.0, self.spec[7] * self.rate)
        peak = 0.0
        for i in range(count):
            base = self.n // self.os
            if base % 32 == 0:
                t = base / self.sr
                self.control(t)
                cents = self.vib_depth * math.sin(2 * math.pi * self.vib_hz * (self.n / self.rate))
                cents += interpolate(self.cents, (self.n - self.cents_at) / self.rate, 1, 0.0)
                self.retune(self.current_hz() * 2 ** (cents / 1200), False)
            if self.os == 2:
                a = self.tick(attack, lift)
                y = self.decimate(a, self.tick(attack, lift))
            else:
                y = self.tick(attack, lift)
            y *= self.gain
            self.tone_y += self.tone_a * (y - self.tone_y)
            s = self.tone_y - self.dc_x + self.dc_r * self.dc_y
            self.dc_x, self.dc_y = self.tone_y, s
            out[i] = s
            peak = max(peak, abs(s))
        if self.n > self.off + self.spec[7] * self.rate and peak < 1e-5:
            self.quiet += count
            if self.quiet >= 2048:
                self.done = True
        else:
            self.quiet = 0
        if self.n >= self.max_seconds * self.rate:
            self.done = True
        return out


def compiled_core():
    """Compile the reference state machine; no fastmath or parallel sample loops."""
    from numba import boolean, float64, int64
    from numba.experimental import jitclass

    floats = (
        "f0 hz from_hz sr rate max_seconds velocity trem_rate trem_phase vib_hz vib_depth "
        "sg sp a tx1 ty1 sy beta from_beta to_beta slur_g slur_p slope vtarget gain "
        "tone_a tone_y lock target bp_b bp_a1 bp_a2 bp_x1 bp_x2 bp_y1 bp_y2 "
        "last_cross dc_r dc_x dc_y stroke_err"
    )
    integers = (
        "os mask nw bw Nn Nb slur_at slur_len cents_at stroke_count stroke_skip n off quiet write"
    )
    fields = [(name, float64) for name in floats.split()]
    fields += [(name, int64) for name in integers.split()]
    fields += [(name, boolean) for name in ("slur_loss", "steady", "done")]
    fields += [(name, float64[::1]) for name in ("spec", "nb", "bb", "taps", "history")]
    fields += [("offsets", int64[::1]), ("controls", float64[:, ::1]), ("cents", float64[:, ::1])]
    return jitclass(fields)(BowCore)
