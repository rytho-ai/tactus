"""A modular, synthetic-source adaptation of Music Agent OS's chop-flip workflow."""

from mix import LEVELS
from parts.bass import add_bass
from parts.chops import add_chops
from parts.drums import add_drums

TRANSPORT = {"bpm": 90.0, "bars": 8, "sample_rate": 48000}


def build(project):
    add_chops(project, gain_db=LEVELS["sample"])
    add_drums(project, gain_db=LEVELS["drums"])
    add_bass(project, gain_db=LEVELS["bass"])
