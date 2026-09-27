"""Compatibility wrapper for `stages.stage_2_extraction.inference`."""

from stages.stage_2_extraction import inference as _impl
from stages.stage_2_extraction.inference import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)

if __name__ == "__main__":
    _impl.main()
