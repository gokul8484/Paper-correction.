"""
OCR service.

Engines
  demo  : reads .txt files directly; for images/PDF with no text layer returns a sample
          handwritten-style answer sheet. Works instantly, no models.
  trocr : OpenCV preprocessing -> line segmentation -> Microsoft TrOCR (handwritten).

Uploaded files are processed in memory and never stored on disk (Render-friendly).
"""
import io
import numpy as np

DEMO_SAMPLE_TEXT = """Q1. Photosynthesis is the process by which green plants make food using sunlight, water and carbon dioxide. Chlorophyll absorbs the light and oxygen is released.
Q2. The CPU is the brain of the computer. It executes instructions and has an ALU for calculations and a control unit.
Q3.
"""


def preprocess_image(img_bgr):
    """OpenCV pipeline: grayscale -> denoise -> adaptive threshold -> deskew."""
    import cv2
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 15, 7, 21)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 15)
    coords = np.column_stack(np.where(binary < 128))
    if len(coords) > 50:
        angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) < 10:   # only fix small tilts
            h, w = binary.shape
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_CUBIC,
                                    borderValue=255)
    return binary


def split_lines(binary):
    """Cut a binary page image into text-line images using horizontal projection."""
    inv = (binary < 128).astype(np.uint8)
    rows = inv.sum(axis=1)
    lines, start = [], None
    for y, v in enumerate(rows):
        if v > 2 and start is None:
            start = y
        elif v <= 2 and start is not None:
            if y - start > 12:
                lines.append(binary[max(0, start - 4): y + 4, :])
            start = None
    if start is not None:
        lines.append(binary[start:, :])
    return lines


_trocr = {}


def _trocr_read(line_img) -> str:
    from PIL import Image
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    if "m" not in _trocr:
        name = "microsoft/trocr-base-handwritten"   # use trocr-small-handwritten for less RAM
        _trocr["p"] = TrOCRProcessor.from_pretrained(name)
        _trocr["m"] = VisionEncoderDecoderModel.from_pretrained(name)
    pil = Image.fromarray(line_img).convert("RGB")
    pixels = _trocr["p"](images=pil, return_tensors="pt").pixel_values
    ids = _trocr["m"].generate(pixels, max_new_tokens=64)
    return _trocr["p"].batch_decode(ids, skip_special_tokens=True)[0]


def _pdf_to_images(data: bytes):
    """Return (embedded_text, [bgr images]) using PyMuPDF (no poppler needed)."""
    import fitz
    import cv2
    doc = fitz.open(stream=data, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc).strip()
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        images.append(cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR))
    return text, images


def extract_text(filename: str, data: bytes, engine: str = "demo") -> str:
    """Main entry point. Raises ValueError with a friendly message on bad files."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "txt":
        return data.decode("utf-8", errors="ignore").strip()

    images, embedded = [], ""
    try:
        if ext == "pdf":
            embedded, images = _pdf_to_images(data)
        else:
            import cv2
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Could not read the image. Upload a valid PNG/JPG.")
            images = [img]
    except ImportError as exc:
        raise ValueError(f"Missing dependency: {exc}") from exc

    if embedded:                       # typed PDFs already contain text
        return embedded
    if engine != "trocr":
        return DEMO_SAMPLE_TEXT.strip()

    out = []
    for img in images:
        for line in split_lines(preprocess_image(img)):
            out.append(_trocr_read(line))
    return "\n".join(out).strip()
