"""Compatibility wrapper for `stages.stage_4_evaluation.prepare_vaipe_sample`."""

from stages.stage_4_evaluation import prepare_vaipe_sample as _impl
from stages.stage_4_evaluation.prepare_vaipe_sample import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)

if __name__ == "__main__":
    _impl.main()
