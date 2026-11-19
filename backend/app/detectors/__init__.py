from app.detectors.base import DetectionContext, Detector
from app.detectors.categories import CategoryDetector
from app.detectors.duplicates import DuplicateDetector
from app.detectors.formats import FormatDetector
from app.detectors.missing import MissingValueDetector
from app.detectors.outliers import OutlierDetector


def default_detectors() -> list[Detector]:
    return [
        MissingValueDetector(),
        FormatDetector(),
        CategoryDetector(),
        OutlierDetector(),
        DuplicateDetector(),
    ]


__all__ = ["DetectionContext", "Detector", "default_detectors"]
