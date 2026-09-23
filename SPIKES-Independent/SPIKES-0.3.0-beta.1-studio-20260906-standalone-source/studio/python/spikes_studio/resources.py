"""Studio assets in source checkouts and relocatable frozen packages."""
from pathlib import Path
import sys


def resource_dir(name):
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'share/spikes/studio'/name
    return Path(__file__).resolve().parents[2]/name
