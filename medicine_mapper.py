"""Compatibility wrapper for `stages.stage_3_mapping.medicine_mapper`."""

from stages.stage_3_mapping import medicine_mapper as _impl
from stages.stage_3_mapping.medicine_mapper import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)

if __name__ == "__main__":
    _impl.main()
