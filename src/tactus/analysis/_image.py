"""Dependency-free, labeled SVG views of analysis matrices; numbers remain authoritative.

PNG heatmap encoding uses stdlib zlib/struct. Rows keep their original index spacing,
with exact center labels; this avoids implying a linear axis for Mel or BPM bins.
Display averages at most 1200 time columns before logarithmic conversion.
"""

import base64
import html
import json
import struct
import zlib

import numpy as np

SUPPORTED = frozenset(
    (
        "spectral.cqt",
        "spectral.vqt",
        "spectral.mel",
        "spectral.chroma",
        "spectral.mfcc",
        "rhythm.tempogram",
    )
)


def _png(rgb):
    def chunk(kind, payload):
        return (
            struct.pack("!I", len(payload))
            + kind
            + payload
            + struct.pack("!I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    height, width, _ = rgb.shape
    raw = b"".join(b"\0" + row.tobytes() for row in rgb)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _colors(values):
    anchors = np.array(
        [[12, 10, 35], [65, 40, 110], [153, 55, 119], [229, 105, 76], [253, 225, 140]]
    )
    return np.stack(
        [np.interp(values, np.linspace(0, 1, len(anchors)), anchors[:, ch]) for ch in range(3)],
        axis=-1,
    ).astype(np.uint8)


def image(
    result: dict, *, title: str = "Analysis", vmin: float | None = None, vmax: float | None = None
) -> str:
    """Return a standalone SVG image from a CQT/VQT, Mel, chroma, MFCC or tempogram result.

    Call after the analysis; input arrays are never modified and no file is written.
    Save the returned string as UTF-8 .svg, or display it with an SVG viewer.
    Magnitude uses 20*log10(max(value, 1e-10)), power uses 10*log10(max(value, 1e-10)),
    both relative to 1 in their feature units (not dBFS). Default Q range -80..0 dB;
    Mel uses peak-80..peak dB (silence -100..-20). Chroma/tempogram use 0..1;
    MFCC uses a symmetric range about zero. vmin/vmax override display bounds in
    these units; reuse both for comparisons. Require finite vmin < vmax.
    At most 1200 time columns, averaged in the numeric domain before conversion;
    full resolution stays in result. Rows are equally spaced by matrix index with
    exact center labels, NOT a linear frequency/BPM axis. SVG metadata records
    scale, bounds and original/display shapes. The image is a view, not an inverse.
    """
    if "magnitude" in result:
        key, axis, label, factor, unit = (
            "magnitude",
            "freqs_hz",
            "Frequency (Hz; log-spaced rows)",
            20,
            "dB re magnitude 1",
        )
    elif "power" in result:
        key, axis, label, factor, unit = (
            "power",
            "freqs_hz",
            "Frequency (Hz; Mel-spaced rows)",
            10,
            "dB re power 1",
        )
    elif "tempogram" in result:
        key, axis, label, factor, unit = (
            "tempogram",
            "bpms",
            "Tempo (BPM; integer-lag rows)",
            0,
            "Relative periodicity",
        )
    elif "chroma" in result:
        key, axis, label, factor, unit = (
            "chroma",
            "pitch_classes",
            "Pitch class",
            0,
            "Relative energy",
        )
    elif "coefficients" in result:
        key, axis, label, factor, unit = (
            "coefficients",
            None,
            "MFCC coefficient",
            0,
            "DCT coefficient",
        )
    else:
        raise ValueError("image requires a CQT/VQT, Mel, chroma, MFCC or tempogram result")
    values = np.asarray(result[key])
    times = np.asarray(result["times_s"], dtype=float)
    if (
        values.dtype.kind not in "fiu"
        or values.ndim != 2
        or not values.size
        or not np.isfinite(values).all()
    ):
        raise ValueError("image matrix must be nonempty, finite and real")
    if (
        times.ndim != 1
        or len(times) != values.shape[1]
        or not np.isfinite(times).all()
        or np.any(np.diff(times) <= 0)
    ):
        raise ValueError("times_s must match columns and be finite and increasing")
    rows = np.asarray(result[axis]) if axis else np.arange(len(values))
    if rows.ndim != 1 or len(rows) != len(values):
        raise ValueError("row labels must match matrix rows")
    if axis != "pitch_classes" and not np.isfinite(rows).all():
        raise ValueError("row coordinates must be finite")
    if key != "coefficients" and np.any(values < 0):
        raise ValueError("image magnitudes, powers and relative strengths must be nonnegative")
    edges = np.linspace(0, values.shape[1], min(1200, values.shape[1]) + 1, dtype=int)
    display = np.add.reduceat(values.astype(float), edges[:-1], axis=1) / np.diff(edges)
    if factor:
        display = factor * np.log10(np.maximum(display, 1e-10))
    if key == "magnitude":
        lower, upper = -80.0, 0.0
    elif key == "power":
        upper = max(-20.0, float(display.max()))
        lower = upper - 80.0
    elif key == "coefficients":
        upper = max(1.0, float(np.abs(display).max()))
        lower = -upper
    else:
        lower, upper = 0.0, 1.0
    lower = lower if vmin is None else float(vmin)
    upper = upper if vmax is None else float(vmax)
    if not np.isfinite([lower, upper]).all() or lower >= upper:
        raise ValueError("image requires finite vmin < vmax")
    pixels = _colors(np.clip((display[::-1] - lower) / (upper - lower), 0, 1))
    png = base64.b64encode(_png(pixels)).decode("ascii")
    legend = base64.b64encode(_png(_colors(np.linspace(1, 0, 256)[:, None]))).decode("ascii")
    meta = {
        "field": key,
        "unit": unit,
        "vmin": lower,
        "vmax": upper,
        "shape": list(values.shape),
        "display_shape": list(display.shape),
        "time_reduction": "block mean before display conversion",
        "row_spacing": "matrix index",
    }
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="540" viewBox="0 0 1120 540" role="img">',
        f"<title>{html.escape(str(title))}</title>",
        f"<metadata>{html.escape(json.dumps(meta))}</metadata>",
        '<rect width="1120" height="540" fill="#111827"/>',
        '<g fill="#e5e7eb" font-family="sans-serif" font-size="13">',
        f'<text x="100" y="30" font-size="20">{html.escape(str(title))}</text>',
        f'<text x="100" y="54">{html.escape(label)}</text>',
        f'<image x="100" y="70" width="860" height="380" preserveAspectRatio="none" href="data:image/png;base64,{png}"/>',
        f'<image x="980" y="70" width="20" height="380" preserveAspectRatio="none" href="data:image/png;base64,{legend}"/>',
        f'<text x="1008" y="80">{upper:.4g}</text>',
        f'<text x="1008" y="450">{lower:.4g}</text>',
        f'<text x="100" y="514">Color: {html.escape(unit)} | range {lower:.4g} to {upper:.4g} | time columns: block mean</text>',
        '<text x="490" y="489">Time (s)</text>',
    ]
    for row in np.unique(np.linspace(0, len(rows) - 1, min(9, len(rows)), dtype=int)):
        text = str(rows[row]) if axis == "pitch_classes" else f"{rows[row]:.4g}"
        y = 70 + 380 * (1 - (row + 0.5) / len(rows))
        parts.append(f'<text x="90" y="{y + 4:.2f}" text-anchor="end">{html.escape(text)}</text>')
    for col in np.unique(np.linspace(0, display.shape[1] - 1, min(6, display.shape[1]), dtype=int)):
        time = (times[edges[col]] + times[edges[col + 1] - 1]) / 2
        x = 100 + 860 * (col + 0.5) / display.shape[1]
        parts.append(f'<text x="{x:.2f}" y="469" text-anchor="middle">{time:.3g}</text>')
    return "\n".join(parts + ["</g></svg>"])
