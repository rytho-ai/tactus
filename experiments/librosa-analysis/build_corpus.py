"""Build 8+ unseen validation loops from real recorded drum one-shots, with known truth.

Each loop is a numpy render at its own sample rate (44100 or 48000, then some resampled
down to 44100 for the final file). Truth onsets are tracked as we place each one-shot.
"""

import json
import os
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

DRUMS = os.environ.get(
    "TACTUS_ONSET_DRUMS",
    str(Path(__file__).resolve().parents[2] / "dogfood/2026-09-25-full-song-2/crate/drums"),
)
OUT = str(
    Path(os.environ.get("TACTUS_ONSET_CORPUS", "dogfood/2026-09-29-librosa-analysis/corpus"))
    / "loops"
)
os.makedirs(OUT, exist_ok=True)

ONESHOTS = {
    "kick_dark": f"{DRUMS}/kicks/Dark_Kick14.wav",
    "kick_kmrebi": f"{DRUMS}/kicks/KMREBI_RHS2_kick_one_shot_best.wav",
    "kick_rack": f"{DRUMS}/kicks/MO_TB_kick_rackfacelift.wav",  # 48k
    "kick_sm101": f"{DRUMS}/kicks/sm101_ck_kick_52.wav",
    "snare_zen": f"{DRUMS}/snares/036_Zenhiser_BK_-_Snare.wav",
    "snare_esm": f"{DRUMS}/snares/ESM_Iconic_Snare_241_Vintage_Gritty_Old_School_Hip_Hop_Bold.wav",
    "snare_trap": f"{DRUMS}/snares/MO_TB_snare_trapsmaccreturns.wav",  # 48k
    "snare_hbk": f"{DRUMS}/snares/hbk_kit05_oneshot_snare02.wav",
    "hat_pitched": f"{DRUMS}/hats/016_Hi_Hat_1_Pitched_-_LDTDM_Zenhiser.wav",
    "hat_open03": f"{DRUMS}/hats/Drums_OneShots_OpenHat_03.wav",
    "hat_esm": f"{DRUMS}/hats/ESM_Iconic_Hi_90_Hit_Hat_Cymbal_Vintage_Vinyl_Gritty.wav",
    "hat_closed": f"{DRUMS}/hats/RKU_LT001_Hihat_Closed_13.wav",
    "hat_open09": f"{DRUMS}/hats/RKU_MTE1_Hihat_Open_09.wav",
    "perc_lock": f"{DRUMS}/percs/MO_BOA_perc_lock.wav",
    "perc_vib": f"{DRUMS}/percs/dh2_perc_nu_vibrator.wav",
    "perc_tread": f"{DRUMS}/percs/lh2_percussion_one_shot_tread.wav",
}
# No toms exist in this crate (drums/ only has hats, snares, kicks, percs) -- noted in report.


def load_mono(path, target_rate):
    x, sr = sf.read(path, dtype="float64", always_2d=True)
    mono = x.mean(axis=1)
    if sr != target_rate:
        from math import gcd

        g = gcd(sr, target_rate)
        mono = resample_poly(mono, target_rate // g, sr // g)
    return mono


def own_attack_offset(mono):
    """First sample where |mono| first reaches 1% of this one-shot's own peak."""
    peak = np.max(np.abs(mono))
    thresh = 0.01 * peak
    idx = np.argmax(np.abs(mono) >= thresh)
    return int(idx)


class LoopBuilder:
    def __init__(self, rate, seconds):
        self.rate = rate
        n = round(seconds * rate)
        self.buf = np.zeros(n, dtype=np.float64)
        self.truth = []  # sorted list of sample-frame onsets

    def ensure_len(self, n):
        if n > len(self.buf):
            self.buf = np.concatenate([self.buf, np.zeros(n - len(self.buf))])

    def place(self, name, at_frame, gain=1.0, mark_truth=True):
        mono = load_mono(ONESHOTS[name], self.rate)
        off = own_attack_offset(mono)
        n = len(mono)
        self.ensure_len(at_frame + n)
        self.buf[at_frame : at_frame + n] += gain * mono
        if mark_truth:
            self.truth.append(at_frame + off)
        return at_frame + off

    def add_bed(self, kind, seconds_start=0.0):
        n = len(self.buf)
        t = np.arange(n) / self.rate
        if kind == "bass":
            bed = 0.12 * np.sin(2 * np.pi * 55.0 * t) * (t >= seconds_start)
            env = np.minimum(1.0, (t - seconds_start).clip(min=0) / 0.05)
            bed *= env
            self.buf[:] += bed
        elif kind == "pad":
            bed = (
                0.06
                * (np.sin(2 * np.pi * 220.0 * t) + np.sin(2 * np.pi * 330.0 * t))
                * (t >= seconds_start)
            )
            env = np.minimum(1.0, (t - seconds_start).clip(min=0) / 0.3)
            bed *= env
            self.buf[:] += bed

    def add_reverb(self, wet=0.25):
        from pedalboard import Pedalboard, Reverb

        board = Pedalboard([Reverb(room_size=0.6, wet_level=wet, dry_level=1.0 - wet, damping=0.4)])
        stereo = np.stack([self.buf, self.buf], axis=0).astype(np.float32)
        out = board(stereo, self.rate)
        self.buf = out.mean(axis=0).astype(np.float64)

    def normalize(self, peak_target=0.85):
        p = np.max(np.abs(self.buf))
        if p > 0:
            self.buf *= peak_target / p

    def finalize_truth(self):
        return sorted(set(self.truth))


def beat_grid(bpm, rate, subdiv=4):
    """Return function step(n) -> sample frame for n subdiv-th notes at bpm."""
    sec_per_beat = 60.0 / bpm
    sec_per_step = sec_per_beat / subdiv
    return round(sec_per_step * rate)


MANIFEST = {}


def save(builder, filename, notes, rate_out=None):
    buf = builder.buf
    rate = builder.rate
    if rate_out and rate_out != rate:
        from math import gcd

        g = gcd(rate, rate_out)
        buf = resample_poly(buf, rate_out // g, rate // g)
        scale = rate_out / rate
        truth = [round(f * scale) for f in builder.finalize_truth()]
        rate = rate_out
    else:
        truth = builder.finalize_truth()
    path = os.path.join(OUT, filename)
    sf.write(path, buf, rate, subtype="FLOAT")
    MANIFEST[filename] = {"rate": rate, "truth_frames": truth, "notes": notes, "length": len(buf)}
    print(filename, "rate", rate, "n_truth", len(truth), "len", len(buf))


# ---------------------------------------------------------------------------
# Loop 1: 100 BPM, kick/snare/hat basic pattern + ghost notes -25dB, native 44.1k
# ---------------------------------------------------------------------------
rate = 44100
bpm = 100
b = LoopBuilder(rate, 4.0)
step16 = beat_grid(bpm, rate, subdiv=4)
bar = step16 * 16
b.place("kick_dark", 0)
b.place("snare_zen", step16 * 4)
b.place("kick_dark", step16 * 8)
b.place("snare_zen", step16 * 12)
for i in range(16):
    b.place("hat_pitched", step16 * i, gain=0.9)
# ghost note ~ -25 dB under a decaying kick tail
b.place("snare_esm", step16 * 6 + step16 // 3, gain=10 ** (-25 / 20))
b.place("kick_dark", bar)
b.place("snare_zen", bar + step16 * 4)
save(b, "loop_01_basic_ghost.wav", "100 BPM basic pattern, native 44.1k, one ghost note -25dB")

# ---------------------------------------------------------------------------
# Loop 2: 128 BPM, flams 12ms apart on snare, overlapping kick tails
# ---------------------------------------------------------------------------
rate = 44100
bpm = 128
b = LoopBuilder(rate, 4.0)
step16 = beat_grid(bpm, rate, subdiv=4)
flam_gap = round(0.012 * rate)  # 12 ms
b.place("kick_kmrebi", 0)
b.place("kick_kmrebi", round(0.09 * rate))  # overlapping tail: 90ms later, same kick
b.place("snare_hbk", step16 * 4 - flam_gap, gain=0.5)  # flam grace note
b.place("snare_hbk", step16 * 4)
b.place("kick_kmrebi", step16 * 8)
b.place("kick_kmrebi", step16 * 8 + round(0.07 * rate))
b.place("snare_hbk", step16 * 12 - flam_gap, gain=0.55)
b.place("snare_hbk", step16 * 12)
for i in range(16):
    b.place("hat_closed", step16 * i, gain=0.85)
save(b, "loop_02_flams_overlap.wav", "128 BPM, 12ms flams, overlapping kick tails, native 44.1k")

# ---------------------------------------------------------------------------
# Loop 3: 160 BPM fast hat rolls (32nd notes) + kick/snare, native 44.1k
# ---------------------------------------------------------------------------
rate = 44100
bpm = 160
b = LoopBuilder(rate, 3.0)
step16 = beat_grid(bpm, rate, subdiv=4)
step32 = beat_grid(bpm, rate, subdiv=8)
b.place("kick_sm101", 0)
b.place("snare_zen", step16 * 4)
b.place("kick_sm101", step16 * 8)
b.place("snare_zen", step16 * 12)
# a roll: 8 32nd-note hats in the 2nd half of the bar
roll_start = step16 * 10
for i in range(8):
    b.place("hat_esm", roll_start + step32 * i, gain=0.8)
for i in range(16):
    if i not in range(10, 14):  # leave the roll region less cluttered
        b.place("hat_open09", step16 * i, gain=0.6)
save(b, "loop_03_hat_roll.wav", "160 BPM, 32nd-note hat roll, native 44.1k")

# ---------------------------------------------------------------------------
# Loop 4: 100 BPM with pedalboard reverb bed, ghost notes -30dB, TUNING loop for librosa
# ---------------------------------------------------------------------------
rate = 48000
bpm = 100
b = LoopBuilder(rate, 4.0)
step16 = beat_grid(bpm, rate, subdiv=4)
b.place("kick_rack", 0)
b.place("snare_trap", step16 * 4)
b.place("kick_rack", step16 * 8)
b.place("snare_trap", step16 * 12)
for i in range(16):
    b.place("hat_pitched", step16 * i, gain=0.85)
b.place("hat_open03", step16 * 6 + step16 // 4, gain=10 ** (-30 / 20))  # ghost, -30dB
b.add_reverb(wet=0.28)
save(b, "loop_04_reverb.wav", "100 BPM, pedalboard Reverb bed, -30dB ghost, native 48k -> kept 48k")

# ---------------------------------------------------------------------------
# Loop 5: 85 BPM slow, bass sine bed underneath, overlapping tails
# ---------------------------------------------------------------------------
rate = 44100
bpm = 85
b = LoopBuilder(rate, 4.5)
step16 = beat_grid(bpm, rate, subdiv=4)
b.place("kick_dark", 0)
b.place("kick_dark", round(0.11 * rate))
b.place("snare_esm", step16 * 4)
b.place("kick_dark", step16 * 8)
b.place("snare_esm", step16 * 12)
for i in range(16):
    b.place("hat_closed", step16 * i, gain=0.8)
b.add_bed("bass", seconds_start=0.0)
save(b, "loop_05_bass_bed.wav", "85 BPM, sine bass bed, overlapping kick tails, native 44.1k")

# ---------------------------------------------------------------------------
# Loop 6: 140 BPM, flams + roll + ghost all combined, then resampled 48k->44.1k
# ---------------------------------------------------------------------------
rate = 48000
bpm = 140
b = LoopBuilder(rate, 3.2)
step16 = beat_grid(bpm, rate, subdiv=4)
step32 = beat_grid(bpm, rate, subdiv=8)
flam_gap = round(0.018 * rate)  # 18ms
b.place("kick_kmrebi", 0)
b.place("snare_hbk", step16 * 4 - flam_gap, gain=0.5)
b.place("snare_hbk", step16 * 4)
b.place("kick_kmrebi", step16 * 8)
b.place("kick_kmrebi", step16 * 8 + round(0.08 * rate))
b.place("snare_hbk", step16 * 12)
roll_start = step16 * 13
for i in range(6):
    b.place("hat_open09", roll_start + step32 * i, gain=0.75)
b.place("perc_lock", step16 * 2 + step16 // 3, gain=10 ** (-22 / 20))  # ghost perc
save(
    b,
    "loop_06_combo.wav",
    "140 BPM combo: flam 18ms + roll + ghost -22dB, rendered 48k -> resampled to 44.1k",
    rate_out=44100,
)

# ---------------------------------------------------------------------------
# Loop 7: 110 BPM percs-heavy pattern, pad bed + reverb, dense overlapping
# ---------------------------------------------------------------------------
rate = 44100
bpm = 110
b = LoopBuilder(rate, 4.0)
step16 = beat_grid(bpm, rate, subdiv=4)
b.place("kick_sm101", 0)
b.place("perc_vib", step16 * 2, gain=0.7)
b.place("snare_zen", step16 * 4)
b.place("perc_tread", step16 * 6, gain=0.6)
b.place("kick_sm101", step16 * 8)
b.place("kick_sm101", step16 * 8 + round(0.08 * rate))  # overlap tail
b.place("perc_vib", step16 * 10, gain=0.7)
b.place("snare_zen", step16 * 12)
b.place("perc_lock", step16 * 6 + step16 // 4, gain=10 ** (-28 / 20))  # ghost under perc_tread tail
for i in range(16):
    b.place("hat_open09", step16 * i, gain=0.55)
b.add_bed("pad", seconds_start=0.0)
b.add_reverb(wet=0.18)
save(
    b,
    "loop_07_perc_pad_reverb.wav",
    "110 BPM percs + pad bed + reverb, ghost -28dB under tail, native 44.1k",
)

# ---------------------------------------------------------------------------
# Loop 8: 150 BPM, everything: flam + roll + ghost + reverb, rendered 48k->44.1k
# ---------------------------------------------------------------------------
rate = 48000
bpm = 150
b = LoopBuilder(rate, 3.2)
step16 = beat_grid(bpm, rate, subdiv=4)
step32 = beat_grid(bpm, rate, subdiv=8)
flam_gap = round(0.008 * rate)  # 8ms, tightest flam
b.place("kick_rack", 0)
b.place("snare_trap", step16 * 4 - flam_gap, gain=0.45)
b.place("snare_trap", step16 * 4)
b.place("kick_rack", step16 * 8)
b.place("kick_rack", step16 * 8 + round(0.06 * rate))
b.place("snare_trap", step16 * 12)
roll_start = step16 * 9
for i in range(10):
    b.place("hat_pitched", roll_start + step32 * i, gain=0.7)
b.place("hat_esm", step16 * 2 + step16 // 3, gain=10 ** (-35 / 20))  # deepest ghost, -35dB
b.add_reverb(wet=0.2)
save(
    b,
    "loop_08_tight_flam_deep_ghost.wav",
    "150 BPM, 8ms flam + roll + -35dB ghost + reverb, rendered 48k -> resampled 44.1k",
    rate_out=44100,
)

# ---------------------------------------------------------------------------
# Loop 9: 95 BPM mixed kit, bass bed + reverb combined, moderate density
# ---------------------------------------------------------------------------
rate = 44100
bpm = 95
b = LoopBuilder(rate, 4.2)
step16 = beat_grid(bpm, rate, subdiv=4)
b.place("kick_dark", 0)
b.place("snare_hbk", step16 * 4)
b.place("kick_dark", step16 * 7)
b.place("kick_dark", step16 * 7 + round(0.1 * rate))
b.place("snare_hbk", step16 * 12)
for i in range(16):
    b.place("hat_open03", step16 * i, gain=0.5)
b.place("perc_tread", step16 * 10 + step16 // 4, gain=10 ** (-24 / 20))
b.add_bed("bass", seconds_start=0.0)
b.add_reverb(wet=0.15)
save(
    b,
    "loop_09_mixed_bass_reverb.wav",
    "95 BPM mixed kit, bass bed + light reverb, ghost -24dB, native 44.1k",
)

with open(os.path.join(OUT, "..", "truth_manifest.json"), "w") as f:
    json.dump(MANIFEST, f, indent=2)
print("wrote manifest with", len(MANIFEST), "loops")
