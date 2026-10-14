"""Built-in delivery exporters that read a run's map: web bundles, subtitles and frame curves.

Each reads a completed run through `export.deliver` and never changes the sound: no
resampling, normalization, mixing or trimming. `web` encodes with an explicit codec
(lossy encoders run through `tool("ffmpeg")` and are decoded again to report their frame
count and offset), `srt` writes a spans lane as subtitles, `curves` samples level analyses
and the map at video-frame times. Picture aesthetics (decay, normalization, smoothing) stay
with the work. `waveform_peaks` is the one owner of the bundle's waveform outline.

Reads: analysis.level · inputs.tool · store.encode_pcm24 · timemap
"""

from __future__ import annotations

import hashlib
import io
import math
import subprocess
import tempfile
from bisect import bisect_right
from itertools import pairwise
from pathlib import Path

import numpy as np
import soundfile as sf

from . import timemap
from ._contracts import write_json
from .store import encode_pcm24

CODECS = {"wav": "wav", "flac": "flac", "aac": "m4a", "opus": "opus"}
_FFMPEG = {"aac": ["-c:a", "aac"], "opus": ["-c:a", "libopus"]}
CURVE_HOP_S = 0.001


def _selected(outputs: dict, names: list[str] | None) -> dict:
    from .export import _selected as selected

    return selected(outputs, names)


def waveform_peaks(audio: np.ndarray, buckets: int) -> list[float]:
    """Largest absolute sample per bucket across channels: an outline, not a waveform.

    The output is split into `min(buckets, frames)` equal integer-edged buckets; values
    are rounded to 4 decimals and are not clipped (headroom above 1 stays visible).
    """
    if type(buckets) is not int or buckets < 1:
        raise ValueError("peaks must be a positive number of buckets")
    samples = np.abs(audio) if audio.ndim == 1 else np.abs(audio).max(axis=1)
    count = min(buckets, len(samples))
    edges = np.linspace(0, len(samples), count + 1).astype(int)
    return [round(float(samples[a:b].max()), 4) for a, b in pairwise(edges)]


def _offset(source: np.ndarray, decoded: np.ndarray, rate: int) -> int | None:
    """Lag (frames) at which `decoded` best matches `source` over its first seconds."""
    a = source.mean(axis=1) if source.ndim == 2 else source
    b = decoded.mean(axis=1) if decoded.ndim == 2 else decoded
    n = min(len(a), len(b), 10 * rate)
    span = min(4096, n // 2)
    a, b = np.asarray(a[:n], dtype=np.float64), np.asarray(b[:n], dtype=np.float64)
    if n < 2 or not np.any(a) or not np.any(b):
        return None
    size = 1 << (2 * n - 1).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    lags = np.concatenate([correlation[: span + 1], correlation[-span:]])
    index = int(np.argmax(lags))
    return index if index <= span else index - len(lags)


def _decode(path: Path, codec: str, channels: int, ffmpeg: Path | None) -> np.ndarray:
    if ffmpeg is None:
        return sf.read(path, dtype="float32", always_2d=True)[0]
    raw = subprocess.run(
        [str(ffmpeg), "-v", "error", "-nostdin", "-i", str(path), "-f", "f32le",
         "-ac", str(channels), "-"],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, channels)


def web(
    outputs,
    sample_rate,
    *,
    out: Path,
    codec: str,
    bitrate: str | None = None,
    names: list[str] | None = None,
    peaks: int = 2000,
    time_map: dict | None = None,
    run_identity: dict | None = None,
) -> dict:
    """Write browser audio and bundle.json: lengths, levels, waveform peaks, map, run identity.

    --codec is required: wav (PCM24, the bytes run publishes), flac (lossless PCM24), aac
    (.m4a) or opus (.opus); aac and opus need --bitrate (e.g. 224k) and are encoded with
    ffmpeg, recorded as a tool. Files are audio/<name>-<sha8>.<ext>, sha8 being the first 8
    hex of the PCM24 WAV sha256 (the run's own WAV name). Each encoded file is decoded again
    and its frame count and offset against the source are reported, not refused; this is
    that decoder's view (ffmpeg keeps AAC's end padding, browsers may trim it). The map is
    copied as frames (`map`) and as seconds (`map_seconds`). No resampling, normalization,
    mixing or trimming. Pass --names as a JSON list to bundle only those outputs.
    """
    if codec not in CODECS:
        raise ValueError(f"codec must be one of {', '.join(CODECS)}")
    lossy = codec in _FFMPEG
    if lossy and not bitrate:
        raise ValueError(f"{codec} needs an explicit --bitrate, e.g. 192k")
    if not lossy and bitrate is not None:
        raise ValueError(f"{codec} is lossless; omit --bitrate")
    selected = _selected(outputs, names)
    ffmpeg = None
    if lossy:
        from .inputs import tool

        ffmpeg = tool("ffmpeg")
    from .analysis import level

    (out / "audio").mkdir()
    entries, mismatched = {}, []
    with tempfile.TemporaryDirectory(prefix="tactus-web-") as temporary:
        for name, audio in selected.items():
            payload, levels = encode_pcm24(audio, sample_rate)
            digest = hashlib.sha256(payload).hexdigest()
            file = out / "audio" / f"{name}-{digest[:8]}.{CODECS[codec]}"
            pcm, _ = sf.read(io.BytesIO(payload), dtype="int32", always_2d=True)
            channels = pcm.shape[1]
            if codec == "wav":
                file.write_bytes(payload)
            elif codec == "flac":
                sf.write(file, pcm, sample_rate, subtype="PCM_24")
            else:
                source = Path(temporary) / f"{name}.wav"
                source.write_bytes(payload)
                subprocess.run(
                    [str(ffmpeg), "-v", "error", "-nostdin", "-y", "-i", str(source),
                     *_FFMPEG[codec], "-b:a", bitrate, str(file)],
                    check=True,
                    capture_output=True,
                )
                source.unlink()
            decoded = _decode(file, codec, channels, ffmpeg)
            reference = pcm.astype(np.float64) / 2**31
            offset = 0 if not lossy else _offset(reference, decoded, sample_rate)
            frames = len(audio)
            if len(decoded) != frames or offset not in (0, None):
                mismatched.append(name)
            entries[name] = {
                "file": file.relative_to(out).as_posix(),
                "codec": codec,
                "bitrate": bitrate,
                "frames": frames,
                "seconds": frames / sample_rate,
                "channels": channels,
                "source_sha256": digest,
                "decoded": {
                    "frames": len(decoded),
                    "offset_frames": offset,
                    "decoder": "ffmpeg" if lossy else "soundfile",
                },
                **levels,
                "integrated_lufs": level.loudness(np.asarray(audio, np.float64), sample_rate)[
                    "integrated_lufs"
                ],
                "peaks": {"buckets": min(peaks, frames), "values": waveform_peaks(audio, peaks)},
            }
    identity = run_identity or {}
    bundle = {
        "kind": "tactus.web-bundle",
        "format_version": 1,
        "source": {
            "run": identity.get("run"),
            "manifest_sha256": identity.get("manifest_sha256"),
            "receipt_sha256": identity.get("receipt_sha256"),
            "map_sha256": identity.get("map_sha256"),
        },
        "sample_rate": sample_rate,
        "outputs": entries,
        "map": time_map,
        "map_seconds": None if time_map is None else timemap.to_seconds(time_map, sample_rate),
    }
    write_json(out / "bundle.json", bundle)
    return {
        "codec": codec,
        "outputs": {name: entry["file"] for name, entry in entries.items()},
        "decoded_mismatch": mismatched,
    }


def _milliseconds(frame: int, rate: int) -> int:
    """Nearest millisecond, an exact half going later (the frame_of rule), in integers."""
    return (2 * frame * 1000 + rate) // (2 * rate)


def _timestamp(ms: int) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _lane(time_map: dict | None, output: str, lane: str, kind: str) -> list[dict]:
    if time_map is None:
        raise ValueError("this run has no map; return one from render to export its lanes")
    lanes = time_map.get("outputs", {}).get(output, {}).get("lanes", {})
    if lane not in lanes:
        raise ValueError(f"the map has no lane {lane!r} on output {output!r}")
    if lanes[lane]["kind"] != kind:
        raise ValueError(f"lane {lane!r} holds {lanes[lane]['kind']}, not {kind}")
    return lanes[lane]["items"]


def srt(
    outputs,
    sample_rate,
    *,
    out: Path,
    output: str,
    lane: str,
    text_field: str = "text",
    time_map: dict | None = None,
) -> dict:
    """Write <lane>.srt from a spans lane of the run's map (e.g. lyric lines).

    Each span becomes one subtitle from its start to its end frame, converted to the nearest
    millisecond (round(frame * 1000 / sample_rate), an exact half going later). Items with
    no nonempty string under --text-field are skipped and counted. SRT cannot carry status:
    items whose `status` is present and not "checked" are written and counted as unsure.
    """
    if output not in outputs:
        raise ValueError(f"no output {output!r} in this run")
    items = _lane(time_map, output, lane, "spans")
    blocks, skipped, unsure = [], 0, 0
    for item in items:
        text = item.get(text_field)
        if not isinstance(text, str) or not text.strip():
            skipped += 1
            continue
        if "status" in item and item["status"] != "checked":
            unsure += 1
        start = _timestamp(_milliseconds(item["start"], sample_rate))
        end = _timestamp(_milliseconds(item["end"], sample_rate))
        blocks.append(f"{len(blocks) + 1}\n{start} --> {end}\n{text.strip()}\n")
    (out / f"{lane}.srt").write_text("\n".join(blocks), encoding="utf-8")
    return {"lines": len(blocks), "skipped": skipped, "unsure": unsure}


def _sample_curve(result: dict, field: str, times: np.ndarray, length: int, rate: int):
    """Values of the analysis window whose centre is nearest each time (frames), or null."""
    values = result[field]
    if not values:
        return [None] * len(times), None
    window, hop = result["window_samples"], result["hop_samples"]
    k = np.clip(np.floor((times - window / 2) / hop + 0.5), 0, len(values) - 1).astype(int)
    centres = k * hop + window / 2
    inside = times < length
    sampled = [values[i] if ok else None for i, ok in zip(k, inside, strict=True)]
    distance = np.abs(centres - times)[inside]
    return sampled, (float(distance.max()) / rate if distance.size else None)


def curves(
    outputs,
    sample_rate,
    *,
    out: Path,
    fps: float,
    names: list[str] | None = None,
    measures: list[str] | None = None,
    events: list[str] | None = None,
    map_output: str | None = None,
    time_map: dict | None = None,
    run_identity: dict | None = None,
) -> dict:
    """Write curves.json: one value per video frame of level analyses and of the map.

    Frame i stands for time i / fps, the moment it is shown; frames cover the longest
    selected output. --measures (JSON list, default ["rms"]) takes rms and/or peak:
    level.rms_curve / level.peak_curve with a window of 1 / fps, evaluated on a 1 ms hop,
    each frame taking the window whose centre is nearest its time (`max_offset_s` reports
    the largest distance), so every value is one the analysis computed; null past an
    output's end or for silence (dBFS). --events (JSON list of points-lane names) gives per
    frame the number of points of that lane falling in the frame's interval, per output.
    The map grid and spans lanes of --map-output (default: the only output the map
    describes) give per frame the bar number, bar and beat phase (beats even within a bar
    unless the grid lists them) and the index of the span sounding. No smoothing,
    normalization or decay: the picture applies its own.
    """
    if type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be a positive number")
    selected = _selected(outputs, names)
    measures = ["rms"] if measures is None else measures
    if not isinstance(measures, list) or not measures or set(measures) - {"rms", "peak"}:
        raise ValueError('measures must be a nonempty list of "rms" and/or "peak"')
    from .analysis import level

    longest = max(len(audio) for audio in selected.values())
    count = math.ceil(longest * fps / sample_rate)
    times = np.arange(count) * (sample_rate / fps)
    analyses = {"rms": (level.rms_curve, "rms_dbfs"), "peak": (level.peak_curve, "sample_peak_dbfs")}
    curves_out = {}
    for name, audio in selected.items():
        for measure in measures:
            fn, field = analyses[measure]
            result = fn(np.asarray(audio), sample_rate, window_s=1 / fps, hop_s=CURVE_HOP_S)
            values, offset = _sample_curve(result, field, times, len(audio), sample_rate)
            curves_out[f"{name}.{field.replace('sample_', '')}"] = {
                "analysis": f"level.{fn.__name__}",
                "revision": fn.revision,
                "window_s": result["window_samples"] / sample_rate,
                "hop_s": result["hop_samples"] / sample_rate,
                "max_offset_s": offset,
                "values": values,
            }
    described = (time_map or {}).get("outputs", {})
    record = {
        "kind": "tactus.curves",
        "format_version": 1,
        "fps": fps,
        "frames": count,
        "frame_time": "start",
        "sample_rate": sample_rate,
        "source": {
            "run": (run_identity or {}).get("run"),
            "manifest_sha256": (run_identity or {}).get("manifest_sha256"),
            "map_sha256": (run_identity or {}).get("map_sha256"),
        },
        "measures": curves_out,
    }
    if events:
        if not isinstance(events, list):
            raise ValueError("events must be a JSON list of points-lane names")
        hits = {}
        for lane in events:
            found = [n for n in selected if lane in described.get(n, {}).get("lanes", {})]
            if not found:
                raise ValueError(f"no selected output's map has a lane {lane!r}")
            for name in found:
                counts = [0] * count
                for item in _lane(time_map, name, lane, "points"):
                    index = math.floor(item["at"] * fps / sample_rate)
                    if index < count:
                        counts[index] += 1
                hits[f"{name}.{lane}"] = {"lane": lane, "hits": counts}
        record["events"] = hits
    if map_output is None and len(described) == 1:
        map_output = next(iter(described))
    elif map_output is not None and map_output not in described:
        raise ValueError(f"the map does not describe output {map_output!r}")
    if map_output is not None:
        entry = described[map_output]
        if "grid" in entry:
            record["grid"] = {"output": map_output, **_grid_frames(entry["grid"], times)}
        spans = {}
        for lane, value in entry.get("lanes", {}).items():
            if value["kind"] == "spans":
                spans[lane] = _span_frames(value["items"], times)
        if spans:
            record["spans"] = {"output": map_output, **spans}
    write_json(out / "curves.json", record)
    return {
        "frames": count,
        "measures": sorted(curves_out),
        "events": sorted(record.get("events", {})),
        "map_output": map_output,
    }


def _grid_frames(grid: dict, times: np.ndarray) -> dict:
    bars, end = grid["bars"], grid.get("end")
    meter = grid.get("beats_per_bar", 4)
    beats = grid.get("beats")
    bar, bar_phase, beat_phase = [], [], []
    for t in times:
        k = bisect_right(bars, t) - 1
        stop = bars[k + 1] if k + 1 < len(bars) else end
        if k < 0 or stop is None or t >= stop or stop == bars[k]:
            bar.append(None)
            bar_phase.append(None)
            beat_phase.append(None)
            continue
        phase = (t - bars[k]) / (stop - bars[k])
        bar.append(grid["first_bar"] + k)
        bar_phase.append(round(phase, 6))
        if beats:
            j = bisect_right(beats, t) - 1
            if 0 <= j < len(beats) - 1:
                beat_phase.append(round((t - beats[j]) / (beats[j + 1] - beats[j]), 6))
            else:
                beat_phase.append(None)
        else:
            quarters = phase * (meter[k] if isinstance(meter, list) else meter)
            beat_phase.append(round(quarters - math.floor(quarters), 6))
    return {"bar": bar, "bar_phase": bar_phase, "beat_phase": beat_phase}


def _span_frames(items: list[dict], times: np.ndarray) -> dict:
    index = []
    for t in times:
        sounding = None
        for i, item in enumerate(items):
            if item["start"] <= t < item["end"]:
                sounding = i
                break
        index.append(sounding)
    return {"index": index, "labels": [item.get("label") for item in items]}
