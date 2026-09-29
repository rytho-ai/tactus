"""A work-owned delivery recipe, selected by `tactus export my-delivery`."""

import json

import soundfile as sf


def bundle(outputs, sample_rate, *, out, title: str = "Demo"):
    """Write a floating-point mix and a small delivery note."""
    sf.write(out / "mix.wav", outputs["mix"], sample_rate, subtype="FLOAT")
    (out / "notes.json").write_text(json.dumps({"title": title, "rate": sample_rate}) + "\n")
    return {"mix": "mix.wav", "notes": "notes.json", "title": title}
