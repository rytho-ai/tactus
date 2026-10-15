"""Versioned data semantics for builtin analyses, independent of drawing and consumers.

The decorator preserves the callable interface and attaches the shared public schema.
Descriptions use resolved results where available; no file/project identity is inferred.
Legacy values stay in place. Selectors distinguish data, coordinates and parameters.
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Any

from . import schema


def _time(*, at, width=None, **extra):
    axis = schema.axis("times_s", "time", "s", "linear", origin="input_start", at=at, **extra)
    if width is not None:
        axis["width"] = width
    return axis


def _level(name, result, rate, params):
    fields, coordinates, parameters = {}, [], []
    scalar = {
        "loudness": ("integrated_lufs", "integrated_loudness", "LUFS", "null"),
        "true_peak": ("true_peak_dbtp", "true_peak", "dBTP", "-inf"),
        "sample_peak": ("sample_peak_dbfs", "sample_peak", "dBFS", "-inf"),
        "rms": ("rms_dbfs", "rms", "dBFS", "-inf"),
        "crest_factor": ("crest_factor_db", "crest_factor", "dB", "null"),
    }
    curves = {
        "momentary_loudness": ("loudness_lufs", "momentary_loudness", "LUFS"),
        "short_term_loudness": ("loudness_lufs", "short_term_loudness", "LUFS"),
        "rms_curve": ("rms_dbfs", "rms", "dBFS"),
        "peak_curve": ("sample_peak_dbfs", "sample_peak", "dBFS"),
        "crest_factor_curve": ("crest_factor_db", "crest_factor", "dB"),
    }
    if name in scalar:
        key, quantity, unit, sentinel = scalar[name]
        meaning = "zero_energy"
        if name == "loudness":
            meaning = "silence_or_insufficient_gated_audio"
        elif name == "crest_factor":
            meaning = "undefined_for_zero_energy"
        fields[key] = schema.summary(quantity, unit, sentinel=sentinel, meaning=meaning)
    elif name in curves:
        key, quantity, unit = curves[name]
        fields[key] = schema.series(
            _time(
                at="end",
                width=result["window_samples"] / rate,
                hop=result["hop_samples"] / rate,
                padding="none",
                end_exclusive=True,
            ),
            schema.value(quantity, unit, sentinel="null", meaning="zero_energy"),
        )
        coordinates = ["times_s"]
        parameters = ["window_samples", "hop_samples"]
    elif name == "loudness_range":
        for key, quantity, unit in (
            ("lra_lu", "loudness_range", "LU"),
            ("low_lufs", "gated_10th_percentile", "LUFS"),
            ("high_lufs", "gated_95th_percentile", "LUFS"),
            ("relative_gate_lufs", "relative_gate", "LUFS"),
        ):
            fields[key] = schema.summary(quantity, unit, sentinel="null", meaning="unavailable")
        fields.update(
            gated_blocks=schema.summary("gated_blocks", "count"),
            duration_s=schema.summary("input_duration", "s"),
            provisional=schema.summary("provisional", "boolean"),
        )
    elif name == "clipping":
        fields = {
            "count": schema.summary("flat_top_runs", "count"),
            "longest": schema.summary("longest_flat_top", "sample"),
            "first_positions": {
                "shape": "events",
                "layout": "rows",
                "limit": 10,
                "x": {
                    "column": 1,
                    "quantity": "time",
                    "unit": "s",
                    "factor": 1 / rate,
                    "origin": "input_start",
                    "at": "start",
                    "width": {"column": 2, "factor": 1 / rate},
                    "end_exclusive": True,
                },
                "attributes": {"channel": {"column": 0, "unit": "index", "index_base": 0}},
            },
        }
    else:
        raise ValueError(f"no schema for level.{name}")
    return fields, coordinates, parameters


def _spectral(name, result, rate, params, frames):
    fields, coordinates, parameters = {}, [], []
    db = schema.value(
        "power_level", "dB re full-scale sine", sentinel="-inf", meaning="zero_energy"
    )
    freq = schema.axis("freqs_hz", "frequency", "Hz", "linear")
    if name == "spectrum":
        fields["level_db"] = schema.series(freq, db)
        coordinates = ["freqs_hz"]
    elif name == "band_levels":
        fields["bands"] = {
            "shape": "series",
            "layout": "records",
            "x": schema.axis("low_hz", "frequency", "Hz", "nonuniform", end_key="high_hz"),
            "y": {"key": "level_db", **db},
            "attributes": {
                "share_db": schema.value(
                    "power_share",
                    "dB re total power",
                    sentinel="-inf",
                    meaning="zero_band_or_total_power",
                )
            },
            "interval": "left_closed_right_open_except_last_closed",
        }
    elif name == "peaks":
        fields["peaks"] = schema.series(
            schema.axis("freq_hz", "frequency", "Hz", "nonuniform"),
            {"key": "level_db", **db},
            layout="records",
            order="descending_level",
        )
    elif name == "tuning":
        for key, unit in (("offset_cents", "cent"), ("offset_semitones", "semitone")):
            fields[key] = schema.summary(
                "tuning_offset",
                unit,
                sentinel="null",
                meaning="no_qualifying_peaks",
                reference="A4 = 440 Hz",
            )
        fields["concentration"] = schema.summary("circular_concentration", "1", range=[0, 1])
        fields["peaks"] = schema.summary("qualifying_peaks", "count")
    elif name in {"centroid", "bandwidth", "rolloff", "flatness"}:
        width = min(2048, frames) if name == "centroid" else result["n_fft"]
        # Legacy centroid lets SciPy shorten nperseg but retains the original
        # noverlap=2048-requested_hop. Its actual hop therefore also changes.
        hop = (
            width - 2048 + max(1, round(params["hop_s"] * rate))
            if name == "centroid"
            else result["hop_samples"]
        )
        key = {
            "centroid": "centroid_hz",
            "bandwidth": "bandwidth_hz",
            "rolloff": "rolloff_hz",
            "flatness": "flatness",
        }[name]
        fields[key] = schema.series(
            _time(at="centre", width=width / rate, hop=hop / rate, padding="zero"),
            schema.value(
                name,
                "1" if name == "flatness" else "Hz",
                sentinel="NaN" if name == "centroid" else "null",
                meaning="undefined_for_zero_power",
                **({"range": [0, 1]} if name == "flatness" else {}),
            ),
        )
        coordinates = ["times_s"]
        parameters = [
            key for key in ("n_fft", "hop_samples", "roll_percent", "floor_ratio") if key in result
        ]
        if name == "centroid":
            fields["first_crossing_s"] = schema.summary(
                "threshold_crossing_time",
                "s",
                sentinel="null",
                meaning="no_threshold_or_no_crossing",
                origin="input_start",
                at="point",
            )
    elif name in {"stft", "mel", "chroma", "mfcc", "cqt", "vqt"}:
        coordinates = ["times_s"]
        if name in {"cqt", "vqt"}:
            time = _time(
                at="centre",
                width={"key": "window_samples", "factor": 1 / rate},
                width_axis="y",
                hop=result["hop_samples"] / rate,
                padding="zero",
            )
            freq["spacing"] = "logarithmic"
            key, y = "magnitude", freq
            value = schema.value("filter_magnitude", "amplitude feature", silence=0)
            parameters = ["window_samples", "hop_samples", "gamma_hz"]
        else:
            time = _time(
                at="centre", width=params["n_fft"] / rate, hop=params["hop"] / rate, padding="zero"
            )
            key = {"stft": "level_db", "mel": "power", "chroma": "chroma", "mfcc": "coefficients"}[
                name
            ]
            y = freq
            if name == "stft":
                value = schema.value(
                    "power_level",
                    "dB re full-scale sine",
                    sentinel="-inf",
                    meaning="zero_energy",
                    array=True,
                )
                fields["duration_s"] = schema.summary("input_duration", "s")
                parameters = ["shape"]
            elif name == "mel":
                y["spacing"] = "nonuniform"
                y["construction"] = "Slaney Mel filter centres"
                value = schema.value("mel_power", "squared FFT magnitude per Hz", silence=0)
            elif name == "chroma":
                y = schema.axis("pitch_classes", "pitch_class", "name", "categorical")
                value = schema.value(
                    "pitch_class_energy",
                    "1",
                    range=[0, 1],
                    normalization="per_frame_max",
                    silence=0,
                )
            else:
                y = {
                    "values": list(range(result[key].shape[0])),
                    "quantity": "coefficient",
                    "unit": "index",
                    "spacing": "linear",
                    "index_base": 0,
                }
                value = schema.value(
                    "mfcc",
                    "orthonormal DCT of log-Mel power",
                    silence="finite; coefficient 0 = -100 * sqrt(n_mels)",
                )
        fields[key] = schema.grid(time, y, value)
        if "key" in y:
            coordinates.append(y["key"])
    else:
        raise ValueError(f"no schema for spectral.{name}")
    return fields, coordinates, parameters


def _rhythm(name, result, rate, params):
    fields, coordinates, parameters = {}, [], []
    if name == "beats":
        time = _time(at="point")
        time.update(key="beats_s", spacing="nonuniform")
        fields["beats_s"] = {"shape": "events", "x": time, "empty": "no_estimates"}
        intervals = _time(at="start", end_exclusive=True)
        intervals.update(
            key="beats_s",
            slice=[0, -1],
            end={"key": "beats_s", "slice": [1, None]},
            spacing="nonuniform",
        )
        fields["tempo_curve"] = schema.series(intervals, schema.value("tempo", "BPM"))
        fields["bpm"] = schema.summary(
            "median_tempo", "BPM", sentinel="null", meaning="fewer_than_two_beats"
        )
    elif name == "onsets":
        time = _time(at="point", hop=result["hop_samples"] / rate)
        time.update(key="onsets_s", spacing="nonuniform")
        fields["onsets_s"] = {"shape": "events", "x": time, "empty": "no_estimates"}
        parameters = ["hop_samples", "fmax_hz"]
    elif name == "onset_strength":
        hop = result["hop_samples"]
        time = _time(at="point", hop=hop / rate)
        # Output j uses frontend frame j - floor(n_fft/(2*hop)); the difference
        # also uses the preceding lag frames. It is not a single centered window.
        time["alignment"] = {
            "frontend": "centred_zero_padded_Hann",
            "window_s": params["n_fft"] / rate,
            "delay_frames": params["n_fft"] // (2 * hop),
            "difference_lag_frames": params["lag"],
        }
        unit = (
            "dB difference" if params["filterbank"] == "mel" else "log10(1 + magnitude) difference"
        )
        fields["strength"] = schema.series(
            time, schema.value("mean_positive_band_difference", unit, silence=0)
        )
        coordinates = ["times_s"]
        parameters = ["hop_samples", "fmax_hz"]
    elif name == "tempogram":
        time = _time(
            at="centre",
            width=result["window_frames"] * result["hop_samples"] / rate,
            hop=result["hop_samples"] / rate,
            padding="zero",
        )
        fields["tempogram"] = schema.grid(
            time,
            schema.axis("bpms", "tempo", "BPM", "nonuniform"),
            schema.value(
                "relative_periodicity",
                "1",
                range=[0, 1],
                normalization="zero_lag_energy",
                silence=0,
            ),
        )
        coordinates = ["times_s", "bpms", "lags"]
        parameters = ["hop_samples", "window_frames"]
    else:
        raise ValueError(f"no schema for rhythm.{name}")
    return fields, coordinates, parameters


def describe(fn):
    """Attach a fresh data schema after a builtin succeeds; preserve signature/revision."""
    signature = inspect.signature(fn)
    category = fn.__module__.rsplit(".", 1)[-1]

    @wraps(fn)
    def described(*args, **kwargs) -> dict[str, Any]:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        result = fn(*args, **kwargs)
        arguments = bound.arguments
        rate = arguments["sample_rate"]
        frames = len(arguments["audio"])
        if category == "spectral":
            fields, coordinates, parameters = _spectral(
                fn.__name__, result, rate, arguments, frames
            )
        elif category == "level":
            fields, coordinates, parameters = _level(fn.__name__, result, rate, arguments)
        else:
            fields, coordinates, parameters = _rhythm(fn.__name__, result, rate, arguments)
        auxiliary = [key for key in parameters if key == "shape"]
        return schema.attach(
            result,
            sample_rate=int(rate),
            frames=frames,
            fields=fields,
            coordinate_keys=coordinates,
            parameter_keys=[key for key in parameters if key not in auxiliary],
            auxiliary_keys=auxiliary,
        )

    described.__doc__ = (fn.__doc__ or "").rstrip() + (
        "\n\n    schema (object): versioned data fields, axes, units, timestamp positions and "
        "special-value encodings; coordinates are relative to this input. "
        "See docs/analysis.md#data-schema.\n"
    )
    return described
