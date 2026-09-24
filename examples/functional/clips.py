"""A clip bank using the same entry contract, with no mix or common output length."""

from parts import RATE, pluck


def render(*, gain=0.6):
    return {
        "sample_rate": RATE,
        "outputs": {
            "short": gain * pluck(220, 0.4),
            "long": gain * pluck(329.63, 1.25),
        },
    }
