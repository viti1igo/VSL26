"""Compatibility wrapper for `stages.stage_2_extraction.llm_extractor`."""

from stages.stage_2_extraction import llm_extractor as _impl
from stages.stage_2_extraction.llm_extractor import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)

if __name__ == "__main__":
    _impl.main()
