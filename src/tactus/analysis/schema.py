"""Shared analysis declarations (schema v1/v2) for builtin and work-local Python results.

Constructors return ordinary dictionaries; attach owns the finite-JSON envelope.
Validation checks declared structure against data, without judging an analysis's
accuracy or inferring missing semantics. Coordinate selectors have one implementation
for root arrays, record keys, row columns and inline values; a selector may take a
`slice`, so a declaration points to existing data instead of copying it. No files are opened.

Reads: numpy · json
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import numpy as np

__all__ = [
    "attach",
    "axis",
    "coordinates",
    "ends",
    "events",
    "grid",
    "series",
    "summary",
    "validate",
    "value",
]


def value(quantity, unit, *, sentinel=None, meaning=None, array=False, **extra):
    """Describe values; optional sentinel names are strings, not nonfinite JSON numbers."""
    special = []
    if sentinel is not None:
        special.append({"python": sentinel, "json": "null", "meaning": meaning})
        if array:
            special[-1]["npz"] = sentinel
    return {"quantity": quantity, "unit": unit, "special_values": special, **extra}


def axis(key=None, quantity=None, unit=None, spacing=None, **extra):
    """Describe coordinates selected by key, inline values or a row column.

    Omitted semantics remain undeclared. Time axes may declare origin, at, width
    and hop; these describe the actual calculation rather than requested settings.
    """
    fields = {"key": key, "quantity": quantity, "unit": unit, "spacing": spacing}
    return {**{k: v for k, v in fields.items() if v is not None}, **extra}


def series(x, y, **extra):
    """Describe a series; y is value semantics, x is a coordinate selector."""
    return {"shape": "series", "x": x, "y": y, **extra}


def grid(x, y, value, *, dimensions=("y", "x")):
    """Describe a matrix with explicit axis order, either (y, x) or (x, y)."""
    return {"shape": "grid", "dimensions": list(dimensions), "x": x, "y": y, "value": value}


def events(x, **extra):
    """Describe points or spans; x may select a record member or tuple column."""
    return {"shape": "events", "x": x, **extra}


def summary(quantity, unit, **extra):
    """Describe a scalar with no plotting axis."""
    return {"shape": "summary", "value": value(quantity, unit, **extra)}


def attach(
    result: dict,
    *,
    sample_rate: int,
    frames: int,
    fields: Mapping[str, dict],
    coordinate_keys=(),
    parameter_keys=(),
    auxiliary_keys=(),
) -> dict:
    """Return a shallow result copy with fresh, validated schema metadata.

    The declaration is version 1, or version 2 when a selector uses `slice` or an axis
    gives interval ends as an `end` selector (so an older reader refuses it instead of
    misreading it).

    Arrays/values are shared unchanged; metadata is copied into finite JSON.
    Explicitly classify every original result key. An existing schema is replaced,
    so derived analyses can redeclare their data without mutating the source result.
    """
    described = {
        **result,
        "schema": _plain(
            {
                "version": 2 if _uses_v2(fields) else 1,
                "input": {
                    "sample_rate": sample_rate,
                    "frames": frames,
                    "time_origin": "input_start",
                },
                "fields": dict(fields),
                "coordinate_keys": list(coordinate_keys),
                "parameter_keys": list(parameter_keys),
                "auxiliary_keys": list(auxiliary_keys),
            }
        ),
    }
    validate(described)
    return described


def coordinates(result: dict, field: str, axis: str = "x") -> np.ndarray:
    """Read a declared coordinate vector, applying selectors and unit factors.

    Operates on direct Python results or data whose NPZ arrays have been loaded.
    Returns an independent array. Never guesses coordinates, aligns origins, opens
    attachment paths or converts units beyond the explicit selector's factor.
    Series y is a value descriptor, not a coordinate axis.
    """
    declaration = _declaration(result)
    if field not in declaration["fields"]:
        _fail(f"schema.fields.{field}", "unknown measurement")
    desc = declaration["fields"][field]
    if not isinstance(desc, dict):
        _fail(f"schema.fields.{field}", "must be an object")
    axes = ("x", "y") if desc.get("shape") == "grid" else ("x",)
    if desc.get("shape") == "summary" or axis not in axes or axis not in desc:
        _fail(f"schema.fields.{field}.{axis}", "coordinate axis is undeclared")
    where = f"schema.fields.{field}.{axis}"
    return _select(result, field, desc, desc[axis], where).copy()


def ends(result: dict, field: str, axis: str = "x") -> np.ndarray:
    """Read the interval ends of a declared axis, in the axis's units.

    Resolved from an `end` selector, `end_key`, or `width` with `at` ("start": start +
    width, "centre": centre + width / 2, "end": the coordinate itself). Point axes and
    axes without width or ends have no interval ends. Returns an independent array.
    """
    declaration = _declaration(result)
    desc = declaration["fields"].get(field)
    where = f"schema.fields.{field}.{axis}"
    if not isinstance(desc, dict) or not isinstance(desc.get(axis), dict):
        _fail(where, "coordinate axis is undeclared")
    spec = desc[axis]
    coords = _select(result, field, desc, spec, where)
    if "end" in spec:
        return _select(result, field, desc, spec["end"], where + ".end").copy()
    if "end_key" in spec:
        selector = {"key": spec["end_key"], **({"factor": spec["factor"]} if "factor" in spec else {})}
        return _select(result, field, desc, selector, where + ".end_key").copy()
    if "width" not in spec or spec.get("width_axis") not in (None, axis):
        _fail(where, "declares no interval ends")
    width = spec["width"]
    if isinstance(width, dict):
        width = _select(result, field, desc, width, where + ".width")
    width = np.asarray(width, dtype=float)
    at = spec.get("at")
    if at == "start":
        return coords + width
    if at == "centre":
        return coords + width / 2
    if at == "end":
        return np.array(coords, dtype=float)
    _fail(where, "declares no interval ends")


def validate(result: dict) -> None:
    """Check v1/v2 declarations, selectors, dimensions and window support; raise ValueError.

    This is structural validation, not proof of correct units, normalization,
    timestamp alignment, sentinel meaning or numerical algorithms. Omitted semantic
    properties stay unknown. Legacy custom results need not opt into this API.
    """
    declaration = _declaration(result)
    source = declaration.get("input")
    if not isinstance(source, dict):
        _fail("schema.input", "must describe sample_rate and frames")
    for name, minimum in (("sample_rate", 1), ("frames", 0)):
        n = source.get(name)
        if type(n) is not int or n < minimum:
            _fail(f"schema.input.{name}", f"must be an integer >= {minimum}")
    fields = declaration["fields"]
    roles = list(fields)
    for role in ("coordinate_keys", "parameter_keys", "auxiliary_keys"):
        keys = declaration.get(role)
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            _fail(f"schema.{role}", "must be a list of result keys")
        roles.extend(keys)
    if len(roles) != len(set(roles)):
        _fail("schema", "field roles must not overlap or repeat")
    if set(roles) != set(result) - {"schema"}:
        _fail("schema", "field roles must classify every result key exactly once")
    for field, desc in fields.items():
        where = f"schema.fields.{field}"
        if not isinstance(desc, dict):
            _fail(where, "must be an object")
        shape = desc.get("shape")
        if shape not in ("series", "grid", "events", "summary"):
            _fail(where + ".shape", "must be series, grid, events or summary")
        data = result[field]
        if _attachment(data):
            _fail(where, "load NPZ attachments before validating data")
        layout = desc.get("layout")
        if layout not in (None, "records", "rows"):
            _fail(where + ".layout", "must be records or rows when supplied")
        if layout and shape not in {"series", "events"}:
            _fail(where + ".layout", "structured layouts require series or events")
        if shape == "summary":
            if np.ndim(data) != 0 or isinstance(data, dict):
                _fail(where, "summary data must be scalar")
            _semantics(desc.get("value", {}), where + ".value")
            continue
        if shape == "grid":
            dims = desc.get("dimensions")
            if dims not in (["y", "x"], ["x", "y"]):
                _fail(where + ".dimensions", "must specify [y, x] or [x, y]")
            if np.ndim(data) != 2:
                _fail(where, "grid data must have two dimensions")
            lengths = dict(zip(dims, np.shape(data), strict=True))
            axes = ("x", "y")
            _semantics(desc.get("value", {}), where + ".value")
        else:
            if layout:
                if not isinstance(data, (list, tuple, np.ndarray)) or (
                    isinstance(data, np.ndarray) and data.ndim == 0
                ):
                    _fail(where, "structured data must be a sequence")
            elif np.ndim(data) != 1:
                _fail(where, "series/events data must be one-dimensional")
            lengths = {"x": len(data)}
            axes = ("x",)
            if shape == "series":
                y = desc.get("y", {})
                _semantics(y, where + ".y")
                if layout:
                    _select(result, field, desc, y, where + ".y")
        for name in axes:
            if name not in desc:
                continue
            spec = desc[name]
            location = f"{where}.{name}"
            _semantics(spec, location)
            coords = _select(result, field, desc, spec, location)
            if len(coords) != lengths[name]:
                _fail(location, "coordinate length must match the data dimension")
            _axis_support(result, field, desc, spec, coords, lengths, location)
        attributes = desc.get("attributes", {})
        if not isinstance(attributes, dict):
            _fail(where + ".attributes", "must be an object")
        for name, spec in attributes.items():
            location = f"{where}.attributes.{name}"
            _semantics(spec, location)
            if layout:
                selector = spec if "key" in spec or "column" in spec else {**spec, "key": name}
                _select(result, field, desc, selector, location)


def _fail(where, message):
    raise ValueError(f"{where}: {message}")


def _plain(item):
    if isinstance(item, np.generic):
        return item.item()
    if isinstance(item, Mapping):
        return {key: _plain(v) for key, v in item.items()}
    if isinstance(item, (list, tuple)):
        return [_plain(v) for v in item]
    return item


def _declaration(result):
    if not isinstance(result, dict) or not isinstance(result.get("schema"), dict):
        _fail("schema", "an explicit declaration is required")
    declaration = result["schema"]
    try:
        json.dumps(declaration, allow_nan=False)
    except (TypeError, ValueError) as exc:
        _fail("schema", f"must contain finite JSON: {exc}")
    if type(declaration.get("version")) is not int or declaration["version"] not in (1, 2):
        _fail("schema.version", "only versions 1 and 2 are supported")
    if not isinstance(declaration.get("fields"), dict):
        _fail("schema.fields", "must be an object")
    if declaration["version"] == 1 and _uses_v2(declaration["fields"]):
        _fail("schema.version", "slice and end selectors need version 2")
    if not all(isinstance(key, str) for key in declaration["fields"]):
        _fail("schema.fields", "measurement keys must be strings")
    return declaration


def _uses_v2(item):
    """Whether a declaration uses a version 2 feature: a `slice` or an `end` selector."""
    if isinstance(item, Mapping):
        if "slice" in item or isinstance(item.get("end"), Mapping):
            return True
        return any(_uses_v2(v) for v in item.values())
    if isinstance(item, (list, tuple)):
        return any(_uses_v2(v) for v in item)
    return False


def _attachment(data):
    return isinstance(data, dict) and {"file", "key", "shape", "dtype"} <= data.keys()


def _select(result, field, desc, selector, where):
    if not isinstance(selector, dict):
        _fail(where, "selector must be an object")
    selected = [k for k in ("key", "values", "column") if k in selector]
    if len(selected) != 1:
        _fail(where, "declare exactly one selector: key, values or column")
    try:
        if "values" in selector:
            data = selector["values"]
        elif "column" in selector:
            column = selector["column"]
            if desc.get("layout") != "rows" or type(column) is not int or column < 0:
                _fail(where, "column requires rows layout and a nonnegative integer")
            data = [row[column] for row in result[field]]
        elif desc.get("layout") == "records":
            data = [row[selector["key"]] for row in result[field]]
        else:
            data = result[selector["key"]]
    except (KeyError, IndexError, TypeError) as exc:
        _fail(where, f"selector cannot be resolved: {exc}")
    if _attachment(data):
        _fail(where, "load NPZ attachments before reading coordinates")
    try:
        vector = np.asarray(data)
    except (ValueError, TypeError) as exc:
        _fail(where, f"selector must resolve to a vector: {exc}")
    if vector.ndim != 1:
        _fail(where, "selector must resolve to a one-dimensional vector")
    if "slice" in selector:
        bounds = selector["slice"]
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(b is None or type(b) is int for b in bounds)
        ):
            _fail(where + ".slice", "must be [start, stop] integers or null")
        vector = vector[bounds[0] : bounds[1]]
    if "factor" in selector:
        factor = selector["factor"]
        if (
            isinstance(factor, bool)
            or not isinstance(factor, (int, float))
            or not np.isfinite(factor)
        ):
            _fail(where + ".factor", "must be a finite number")
        try:
            vector = vector * factor
        except (ValueError, TypeError) as exc:
            _fail(where, f"cannot apply factor: {exc}")
    return vector


def _semantics(spec, where):
    if not isinstance(spec, dict):
        _fail(where, "must be an object")
    for name in ("quantity", "unit", "origin"):
        if name in spec and (not isinstance(spec[name], str) or not spec[name]):
            _fail(where + "." + name, "must be a nonempty string when declared")
    if "spacing" in spec and spec["spacing"] not in (
        "linear",
        "logarithmic",
        "nonuniform",
        "categorical",
    ):
        _fail(where + ".spacing", "unsupported coordinate spacing")
    if "at" in spec and spec["at"] not in ("centre", "start", "end", "point"):
        _fail(where + ".at", "must be centre, start, end or point")


def _axis_support(result, field, desc, spec, coords, lengths, where):
    if (
        (
            spec.get("quantity") == "time"
            or spec.get("spacing") in ("linear", "logarithmic", "nonuniform")
        )
        and coords.size
        and (coords.dtype.kind not in "iuf" or not np.isfinite(coords).all())
    ):
        _fail(where, "numeric coordinates must be finite; use categorical spacing for labels")
    if spec.get("at") in {"start", "end"} and not {"width", "end_key", "end"} & spec.keys():
        _fail(where, "start/end timestamps require width, end_key or end")
    if "hop" in spec and (
        isinstance(spec["hop"], bool)
        or not isinstance(spec["hop"], (int, float))
        or spec["hop"] <= 0
    ):
        _fail(where + ".hop", "must be positive seconds")
    if "width_axis" in spec and (
        "width" not in spec
        or not isinstance(spec["width_axis"], str)
        or spec["width_axis"] not in lengths
    ):
        _fail(where + ".width_axis", "must name an existing dimension with width supplied")
    if "width" in spec:
        width = spec["width"]
        if isinstance(width, dict):
            width = _select(result, field, desc, width, where + ".width")
        widths = np.asarray(width)
        if widths.dtype.kind not in "iuf" or not np.isfinite(widths).all() or np.any(widths < 0):
            _fail(where + ".width", "must contain finite nonnegative seconds")
        count = lengths[spec["width_axis"]] if "width_axis" in spec else len(coords)
        if widths.ndim > 1 or (widths.ndim == 1 and len(widths) != count):
            _fail(where + ".width", "width count must match its declared dimension")
    if "end" in spec:
        if "end_key" in spec:
            _fail(where, "declare end or end_key, not both")
        ends = _select(result, field, desc, spec["end"], where + ".end")
        if len(ends) != len(coords) or ends.dtype.kind not in "iuf" or not np.isfinite(ends).all():
            _fail(where + ".end", "interval ends must be finite and match coordinates")
        if np.any(ends < coords):
            _fail(where + ".end", "interval ends must not precede starts")
    if "end_key" in spec:
        selector = {"key": spec["end_key"]}
        if "factor" in spec:
            selector["factor"] = spec["factor"]
        ends = _select(result, field, desc, selector, where + ".end_key")
        if len(ends) != len(coords) or ends.dtype.kind not in "iuf" or not np.isfinite(ends).all():
            _fail(where + ".end_key", "interval ends must be finite and match coordinates")
        if np.any(ends < coords):
            _fail(where + ".end_key", "interval ends must not precede starts")
