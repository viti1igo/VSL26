"""Compatibility wrapper for `stages.stage_4_evaluation.compare_extraction_methods`."""

from stages.stage_4_evaluation import compare_extraction_methods as _impl
from stages.stage_4_evaluation.compare_extraction_methods import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)

if __name__ == "__main__":
    _impl.main()
