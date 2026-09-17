from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.exceptions import AppError


@dataclass(frozen=True, slots=True)
class OCRResult:
    text: str
    average_confidence: float | None
    line_count: int


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:  # pragma: no cover - deployment configuration guard
        raise AppError("OCR组件未安装，请按部署文档安装本地OCR依赖", code=4025) from exc
    return RapidOCR()


def recognize_image(image: bytes) -> OCRResult:
    if not settings.ocr_enabled:
        raise AppError("当前环境未启用OCR，请上传文字版PDF、DOCX或TXT", code=4025)
    try:
        with Image.open(BytesIO(image)) as parsed:
            width, height = parsed.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AppError("图片无法读取，请上传有效的PNG、JPG、WEBP或BMP文件", code=4024) from exc
    if width <= 0 or height <= 0 or width * height > settings.ocr_max_image_pixels:
        raise AppError("图片像素过大，请压缩到2000万像素以内后重试", code=4026)
    try:
        output = _engine()(image, text_score=settings.ocr_min_confidence)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("OCR识别失败，请上传更清晰的原图或文字版文档", code=4025) from exc
    texts = tuple(output.txts or ())
    scores = tuple(float(score) for score in (output.scores or ()))
    accepted = [
        (text.strip(), scores[index] if index < len(scores) else None)
        for index, text in enumerate(texts)
        if text.strip() and (index >= len(scores) or scores[index] >= settings.ocr_min_confidence)
    ]
    confidences = [confidence for _, confidence in accepted if confidence is not None]
    return OCRResult(
        text="\n".join(text for text, _ in accepted),
        average_confidence=(sum(confidences) / len(confidences) if confidences else None),
        line_count=len(accepted),
    )


def marked_ocr_text(result: OCRResult) -> str:
    confidence = (
        f"{result.average_confidence:.0%}" if result.average_confidence is not None else "未提供"
    )
    return f"[OCR识别文本｜平均置信度 {confidence}｜请对照原图复核]\n{result.text}"
