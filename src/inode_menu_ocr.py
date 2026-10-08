"""Read only the supplied local menu image using installed, bundled OCR models."""
import json
import sys

from rapidocr_onnxruntime import RapidOCR
import cv2


def recognize(path, kind="menu"):
    engine = RapidOCR()
    image = cv2.imread(path)
    if image is None:
        raise ValueError("Menu image could not be read")
    expected = ["\u663e\u793a\u5feb\u6377\u680f", "\u7f51\u7edc\u63a5\u5165", "\u5173\u4e8e", "\u9000\u51fa"]
    lines = []
    for scale in (1, 2 / 3):
        result, _ = engine(cv2.resize(image, None, fx=scale, fy=scale))
        lines = sorted([
            {
                "Text": "".join(text.split()),
                "Confidence": float(confidence),
                "X": round(sum(point[0] for point in box) / (4 * scale)),
                "Y": round(sum(point[1] for point in box) / (4 * scale)),
            }
            for box, text, confidence in (result or [])
        ], key=lambda line: line["Y"])
        if kind == "dialog":
            return lines
        if [line["Text"] for line in lines] == expected and min(line["Confidence"] for line in lines) >= 0.6:
            return lines
    return lines


if __name__ == "__main__":
    print(json.dumps(recognize(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "menu"), ensure_ascii=True))
