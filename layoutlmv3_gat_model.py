"""Compatibility wrapper for `stages.stage_2_extraction.layoutlmv3_gat_model`."""

from stages.stage_2_extraction import layoutlmv3_gat_model as _impl
from stages.stage_2_extraction.layoutlmv3_gat_model import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)
