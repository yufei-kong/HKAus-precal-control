"""
Device drivers package for HyperK DAQ system
"""

from .caen_dt5533e import DT5533E

try:
    from .siggen_sdg1032x import SiglentSDG1032X
    __all__ = ['DT5533E', 'SiglentSDG1032X']
except ImportError:
    # Signal generator driver not available
    __all__ = ['DT5533E']