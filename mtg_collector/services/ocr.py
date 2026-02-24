"""Local OCR for reading card text from images using RapidOCR (PP-OCRv4 via ONNX Runtime)."""

from rapidocr import LangRec, RapidOCR

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is not None:
        return _ocr
    _ocr = RapidOCR(params={
        "Global.use_cls": True,
        "Global.log_level": "critical",
        "Rec.lang_type": LangRec.EN,
    })
    return _ocr


def run_ocr(image_path: str) -> list[str]:
    """
    Run OCR on an image and return extracted text fragments.

    Args:
        image_path: Path to the image file

    Returns:
        List of text strings found in the image
    """
    result = _get_ocr()(image_path)
    return list(result.txts) if result.txts else []


def run_ocr_with_boxes(image_path: str) -> list[dict]:
    """
    Run OCR on an image and return text fragments with bounding boxes.

    Returns:
        List of dicts with keys: text, bbox ({x, y, w, h}), confidence
    """
    result = _get_ocr()(image_path)
    fragments = []
    if result.boxes is not None and result.txts is not None:
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            fragments.append({
                "text": text,
                "bbox": {
                    "x": float(min(xs)),
                    "y": float(min(ys)),
                    "w": float(max(xs) - min(xs)),
                    "h": float(max(ys) - min(ys)),
                },
                "confidence": round(float(score), 3),
            })
    return fragments
