"""Compatibility wrapper for `stages.stage_1_ocr.ocr_engine`."""

from stages.stage_1_ocr import ocr_engine as _impl
from stages.stage_1_ocr.ocr_engine import *  # noqa: F401,F403

globals().update(
    {
        name: value
        for name, value in vars(_impl).items()
        if name.startswith("_") and not name.startswith("__")
    }
)

if __name__ == "__main__":
    _impl.main()
