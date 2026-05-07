from __future__ import annotations

import hashlib
import pickle
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Easy-to-edit demo switches.
USE_FACE_RECOGNITION = False
MOCK_FACE_PREFIX = b"mock-face:"


def _load_face_recognition():
    import face_recognition  # type: ignore

    return face_recognition


def load_image_array(image_bytes: bytes) -> np.ndarray:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    return np.array(image)


def image_array_to_bytes(image: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    return buffer.getvalue()


def _mock_encoding_from_image(image: np.ndarray) -> np.ndarray:
    resized = Image.fromarray(image).resize((16, 16)).convert("L")
    arr = np.asarray(resized, dtype=np.float32).reshape(-1)
    arr = arr / 255.0
    return arr


def _mock_face_locations(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    height, width = image.shape[:2]
    return [(0, width, height, 0)]


def get_face_encoding(image):
    if USE_FACE_RECOGNITION:
        face_recognition = _load_face_recognition()
        encodings = face_recognition.face_encodings(image)
        if len(encodings) > 0:
            return encodings[0]
        return None
    return _mock_encoding_from_image(image)


def detect_faces(image):
    if USE_FACE_RECOGNITION:
        face_recognition = _load_face_recognition()
        locs = face_recognition.face_locations(image)
        encodings = face_recognition.face_encodings(image, locs)
        return locs, encodings
    return _mock_face_locations(image), [_mock_encoding_from_image(image)]


def detect_face(image):
    locations, encodings = detect_faces(image)
    if len(encodings) > 0:
        return locations[0], encodings[0]
    return None, None


def analyze_image(image_bytes: bytes):
    image = load_image_array(image_bytes)
    locations, encodings = detect_faces(image)
    warnings: list[str] = []
    if len(locations) == 0:
        warnings.append("No face found in the image.")
    elif len(locations) > 1:
        warnings.append("Multiple faces detected. Use a single face image.")
    encoding = encodings[0] if encodings else None
    return image, locations, encoding, warnings


def annotate_face_boxes(image: np.ndarray, face_locations) -> Image.Image:
    pil_image = Image.fromarray(image.copy())
    draw = ImageDraw.Draw(pil_image)
    for top, right, bottom, left in face_locations:
        draw.rectangle([left, top, right, bottom], outline=(0, 255, 0), width=3)
    return pil_image


def crop_face(image, face_location):
    top, right, bottom, left = face_location
    return image[top:bottom, left:right]


def image_array_to_encoding_blob(image: np.ndarray):
    encoding = get_face_encoding(image)
    if encoding is None:
        raise ValueError("No face found in the uploaded image.")
    return encode_to_blob(encoding)


def encode_to_blob(encoding):
    return pickle.dumps(encoding)


def decode_blob(blob):
    return pickle.loads(blob)


def compare_faces(known_encodings, face_encoding):
    if len(known_encodings) == 0:
        return None

    if USE_FACE_RECOGNITION:
        face_recognition = _load_face_recognition()
        matches = face_recognition.compare_faces(known_encodings, face_encoding)
        face_distances = face_recognition.face_distance(known_encodings, face_encoding)
        if len(face_distances) == 0:
            return None
        best_match = int(np.argmin(face_distances))
        if matches[best_match]:
            return best_match
        return None

    distances = [float(np.linalg.norm(np.asarray(known) - np.asarray(face_encoding))) for known in known_encodings]
    best_match = int(np.argmin(distances))
    if distances[best_match] <= 2.5:
        return best_match
    return None


def image_bytes_to_encoding_blob(image_bytes: bytes):
    image = load_image_array(image_bytes)
    return image_array_to_encoding_blob(image)


def compare_image_with_blob(image_bytes: bytes, known_encoding_blob: bytes) -> bool:
    image, locations, encoding, _ = analyze_image(image_bytes)
    if len(locations) != 1 or encoding is None:
        return False
    known_encoding = decode_blob(known_encoding_blob)
    return compare_faces([known_encoding], encoding) is not None


def save_encoding_blob(path: Path, encoding_blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoding_blob)


def mock_face_encoding_blob(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return MOCK_FACE_PREFIX + digest
