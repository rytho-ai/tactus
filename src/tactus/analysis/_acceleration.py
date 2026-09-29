"""Bounded automatic FFT parallelism; honor nondefault SciPy worker contexts."""

from scipy.fft import get_workers


def fft_workers(work: int) -> int:
    """Four native workers for at least 2**20 frame samples; no global mutation."""
    configured = get_workers()
    return 4 if configured == 1 and work >= 2**20 else configured
