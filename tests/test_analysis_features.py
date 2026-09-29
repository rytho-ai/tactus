"""Owned feature contracts, optional reference comparisons and actual CLI artifacts."""

from __future__ import annotations

import json

import numpy as np
import pytest
import soundfile as sf
from scipy.fft import dct

from tactus.analysis import rhythm, spectral
from tactus.cli import main
from tactus.inputs.pool import hash_file

FUNCTIONS = (spectral.mel, spectral.chroma, spectral.mfcc, rhythm.onset_strength, rhythm.onsets)


def tone(rate, frequency, duration=0.6):
    return 0.2 * np.sin(2 * np.pi * frequency * np.arange(round(rate * duration)) / rate)


@pytest.mark.parametrize("rate", [22050, 44100, 48000])
@pytest.mark.reference
def test_spectral_matrices_match_direct_librosa_and_preserve_input(rate, librosa):
    x = np.column_stack([tone(rate, 440), tone(rate, 660)])
    before = x.copy()
    y = x.sum(axis=1)
    kwargs = {"n_fft": 1024, "hop": 128}
    direct = {
        "n_fft": 1024,
        "hop_length": 128,
        "center": True,
        "pad_mode": "constant",
        "window": "hann",
    }
    power = librosa.feature.melspectrogram(
        y=y,
        sr=rate,
        n_mels=40,
        fmin=80,
        fmax=8000,
        power=2,
        htk=False,
        norm="slaney",
        **direct,
    )
    result = spectral.mel(x, rate, n_mels=40, fmin=80, fmax=8000, **kwargs)
    np.testing.assert_allclose(result["power"], power, rtol=1e-12, atol=1e-14)
    np.testing.assert_allclose(result["times_s"], np.arange(power.shape[1]) * 128 / rate)
    expected = librosa.feature.mfcc(
        S=librosa.power_to_db(power, ref=1, amin=1e-10, top_db=80),
        n_mfcc=13,
        dct_type=2,
        norm="ortho",
        lifter=0,
    )
    result = spectral.mfcc(x, rate, n_mels=40, n_mfcc=13, fmin=80, fmax=8000, **kwargs)
    np.testing.assert_allclose(result["coefficients"], expected, atol=1e-12)
    chroma = spectral.chroma(x, rate, tuning=0.15, **kwargs)
    expected = librosa.feature.chroma_stft(y=y, sr=rate, tuning=0.15, **direct)
    np.testing.assert_allclose(chroma["chroma"], expected, atol=1e-12)
    np.testing.assert_array_equal(x, before)


def test_mel_localizes_a_tone_and_mfcc_is_the_documented_dct():
    audio = tone(48000, 1000, 1)
    mel = spectral.mel(audio, 48000)
    peak_band = np.argmax(mel["power"][:, 2:-2].mean(axis=1))
    assert abs(mel["freqs_hz"][peak_band] - 1000) < 100
    # Independent transform: floor and 80 dB clipping followed by scipy's DCT.
    log_power = 10 * np.log10(np.maximum(1e-10, mel["power"]))
    log_power = np.maximum(log_power, log_power.max() - 80)
    expected = dct(log_power, type=2, norm="ortho", axis=0)[:20]
    np.testing.assert_allclose(spectral.mfcc(audio, 48000)["coefficients"], expected, atol=1e-12)


@pytest.mark.parametrize("midi", [60, 64, 69, 72])
def test_chroma_tracks_pitch_class_in_c_first_order(midi):
    result = spectral.chroma(tone(22050, 440 * 2 ** ((midi - 69) / 12), 1), 22050)
    assert np.argmax(result["chroma"][:, 3:-3].mean(axis=1)) == midi % 12
    np.testing.assert_allclose(result["chroma"].max(axis=0), 1)
    assert result["pitch_classes"][0] == "C"


@pytest.mark.parametrize("length", [1, 511, 512, 1024, 2049])
def test_silence_short_inputs_and_centered_frame_grid(length):
    audio = np.zeros((length, 2))
    for fn, field in ((spectral.mel, "power"), (spectral.chroma, "chroma")):
        result = fn(audio, 22050)
        assert result[field].shape[1] == length // 512 + 1
        assert not result[field].any()
        np.testing.assert_array_equal(result["times_s"], np.arange(length // 512 + 1) * 512 / 22050)
    mfcc = spectral.mfcc(audio, 22050)["coefficients"]
    np.testing.assert_allclose(mfcc[0], -100 * np.sqrt(128))
    np.testing.assert_allclose(mfcc[1:], 0, atol=1e-10)
    assert rhythm.onsets(audio, 22050)["onsets_s"] == []
    assert not np.any(rhythm.onset_strength(audio, 22050)["strength"])


@pytest.mark.reference
def test_short_nonzero_signal_matches_librosa_padding(librosa):
    audio = np.array([0.2, -0.1, 0.3])
    with pytest.warns(UserWarning, match="n_fft"):
        expected = librosa.feature.melspectrogram(y=audio, sr=22050)
    np.testing.assert_allclose(spectral.mel(audio, 22050)["power"], expected)


@pytest.mark.parametrize("fn", FUNCTIONS)
def test_phase_cancelled_channels_produce_silence(fn):
    x = tone(22050, 440)
    stereo = np.column_stack([x, -x])
    silent = fn(np.zeros(len(x)), 22050)
    actual = fn(stereo, 22050)
    for key in actual:
        if isinstance(actual[key], (list, np.ndarray)) and key != "pitch_classes":
            np.testing.assert_allclose(actual[key], silent[key])


@pytest.mark.parametrize("rate", [22050, 44100, 48000])
@pytest.mark.reference
def test_onsets_match_explicit_librosa_frontend_and_peak_picker(rate, librosa):
    audio = tone(rate, 220, 1)
    audio[round(rate * 0.3)] += 2
    audio[round(rate * 0.7)] += 2
    stereo = np.column_stack([audio, audio * 0.4])
    mono = stereo.mean(axis=1)
    hop = round(rate * 0.005)
    power = librosa.feature.melspectrogram(
        y=mono,
        sr=rate,
        n_fft=1024,
        hop_length=hop,
        n_mels=138,
        fmin=27.5,
        fmax=min(16000, rate / 2),
        htk=False,
        norm="slaney",
    )
    expected = librosa.onset.onset_strength(
        S=librosa.power_to_db(power, ref=np.max),
        sr=rate,
        n_fft=1024,
        hop_length=hop,
        lag=2,
        max_size=3,
    )
    result = rhythm.onset_strength(stereo, rate)
    np.testing.assert_allclose(result["strength"], expected, atol=1e-12)
    assert result["hop_samples"] == hop
    assert result["fmax_hz"] == min(16000, rate / 2)
    for backtrack in (False, True):
        frames = librosa.onset.onset_detect(
            onset_envelope=expected,
            sr=rate,
            hop_length=hop,
            backtrack=backtrack,
            delta=0.04,
            wait=int(0.01 * rate // hop),
        )
        times = np.unique(frames[frames * hop < len(audio)]) * hop / rate
        result = rhythm.onsets(stereo, rate, delta=0.04, min_interval_s=0.01, backtrack=backtrack)
        np.testing.assert_array_equal(result["onsets_s"], times)


def test_isolated_attacks_and_backtracking_within_the_signal():
    rate = 48000
    audio = np.zeros(rate * 2)
    truth = np.array([0.25, 0.65, 1.15, 1.6])
    audio[(truth * rate).astype(int)] = 1
    result = rhythm.onsets(audio, rate)["onsets_s"]
    assert len(result) == len(truth)
    np.testing.assert_allclose(result, truth, atol=0.015)
    backtracked = rhythm.onsets(audio, rate, backtrack=True)["onsets_s"]
    assert len(backtracked) == len(result)
    assert np.all(np.asarray(backtracked) <= result)
    assert 0 <= backtracked[0] < backtracked[-1] < 2


@pytest.mark.parametrize("fn", FUNCTIONS)
@pytest.mark.parametrize(
    "audio,rate",
    [
        (np.array([]), 22050),
        (np.zeros((2, 0)), 22050),
        (np.zeros((2, 2, 2)), 22050),
        (np.array([np.nan]), 22050),
        (np.array([np.inf]), 22050),
        (np.array([1j]), 22050),
        (np.zeros(10), 0),
        (np.zeros(10), 22050.5),
    ],
)
def test_invalid_audio_and_rate(fn, audio, rate):
    with pytest.raises(ValueError):
        fn(audio, rate)


@pytest.mark.parametrize(
    "fn,params",
    [
        (spectral.mel, {"n_fft": 0}),
        (spectral.mel, {"n_fft": 511}),
        (spectral.mel, {"hop": 0}),
        (spectral.mel, {"hop": 4096}),
        (spectral.mel, {"fmax": 30000}),
        (spectral.mel, {"fmin": -1}),
        (spectral.mel, {"fmax": float("nan")}),
        (spectral.mel, {"n_mels": 0}),
        (spectral.mfcc, {"n_mfcc": 129}),
        (spectral.mfcc, {"n_mfcc": 0}),
        (spectral.chroma, {"tuning": float("inf")}),
        (rhythm.onsets, {"delta": -1}),
        (rhythm.onsets, {"min_interval_s": -1}),
        (rhythm.onset_strength, {"hop_s": 0}),
        (rhythm.onset_strength, {"lag": 0}),
        (rhythm.onset_strength, {"max_size": 0}),
    ],
)
def test_invalid_parameters(fn, params):
    with pytest.raises(ValueError):
        fn(np.zeros(4096), 22050, **params)


@pytest.mark.parametrize("name", ["mel", "chroma", "mfcc"])
def test_cli_matrix_attachments_equal_python_and_include_provenance(name, tmp_path, capsys):
    wav = tmp_path / "audio.wav"
    sf.write(wav, tone(22050, 440), 22050, subtype="FLOAT")
    command = ["analyze", "spectral", name, str(wav)]
    assert main(command) == 1
    assert "--out" in capsys.readouterr().out
    out = tmp_path / "features"
    assert main([*command, "--hop", "256", "--out", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    audio, rate = sf.read(wav)
    expected = getattr(spectral, name)(audio, rate, hop=256)
    for key, value in expected.items():
        if isinstance(value, np.ndarray):
            descriptor = report["result"][key]
            with np.load(descriptor["file"], allow_pickle=False) as arrays:
                np.testing.assert_array_equal(arrays[descriptor["key"]], value)
            assert descriptor["shape"] == list(value.shape)
        else:
            assert report["result"][key] == value
    assert report["artifacts"]["arrays.npz"]["sha256"] == hash_file(next(out.rglob("arrays.npz")))
    assert report["revision"] == 1
    assert report["params"]["hop"] == 256
    assert report["input_sha256"] == hash_file(wav)
    assert report["provenance"]["callable"]["callable"].endswith(f":{name}")


@pytest.mark.parametrize(
    "category,name",
    [
        ("spectral", "mel"),
        ("spectral", "chroma"),
        ("spectral", "mfcc"),
        ("rhythm", "onsets"),
        ("rhythm", "onset_strength"),
    ],
)
def test_generated_cli_help_and_registry(category, name, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["analyze", category, name, "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--n-fft" in help_text and "Returns:" in help_text


def test_cli_onsets_on_saved_run_and_invalid_parameter(tmp_path, capsys):
    song = tmp_path / "song.py"
    song.write_text("""import numpy as np
def render():
    x = np.zeros(48000)
    x[[12000, 36000]] = 0.9
    return {"sample_rate": 48000, "outputs": {"hits": x, "silent": x*0}}
""")
    run = tmp_path / "run"
    assert main(["run", str(song), "--out", str(run)]) == 0
    capsys.readouterr()
    assert main(["analyze", "rhythm", "onsets", str(run), "--backtrack"]) == 0
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["output"] for r in reports] == ["hits", "silent"]
    assert len(reports[0]["result"]["onsets_s"]) == 2
    assert reports[1]["result"]["onsets_s"] == []
    assert all(r["params"]["backtrack"] for r in reports)
    assert main(["analyze", "rhythm", "onsets", reports[0]["path"], "--delta", "-1"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "analysis_failed"
