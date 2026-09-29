"""Cached double-precision Q correlations; no fastmath or FFT approximation.

Packed kernels avoid padding every filter to the longest window. The caller owns
validation, workload selection and a temporary, restored Numba thread mask.
"""

import numpy as np
from numba import njit, prange


@njit(cache=True, parallel=True)
def correlations(x, real, imag, starts, hop):
    count = 1 + len(x) // hop
    result = np.empty((len(starts) - 1, count))
    for row in prange(len(starts) - 1):
        base = starts[row]
        size = starts[row + 1] - base
        for frame in range(count):
            start = frame * hop - size // 2
            re = 0.0
            im = 0.0
            for k in range(max(0, -start), min(size, len(x) - start)):
                re += x[start + k] * real[base + k]
                im += x[start + k] * imag[base + k]
            result[row, frame] = np.hypot(re, im)
    return result
