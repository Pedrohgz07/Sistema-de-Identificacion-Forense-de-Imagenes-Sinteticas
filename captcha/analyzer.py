import json
import numpy as np
from PIL import Image, ImageChops
import tensorflow as tf
from io import BytesIO
import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "model" / "modelo_ai_vs_real.keras"
THRESHOLD_PATH = BASE_DIR / "model" / "umbral_optimo.json"


def cargar_umbral_decision() -> float:
    try:
        with THRESHOLD_PATH.open(encoding="utf-8") as archivo:
            valor = float(json.load(archivo)["DECISION_THRESHOLD"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"No se pudo cargar un DECISION_THRESHOLD válido desde {THRESHOLD_PATH}"
        ) from e

    if not 0.0 <= valor <= 1.0:
        raise RuntimeError("DECISION_THRESHOLD debe estar entre 0 y 1.")
    return valor


DECISION_THRESHOLD = cargar_umbral_decision()

try:
    model = tf.keras.models.load_model(MODEL_PATH)
except Exception as e:
    model = None
    print(f"[ERROR] No se pudo cargar el modelo: {e}")

def ela_analysis(img: Image.Image, quality: int = 90) -> str:

    img_rgb = img.convert("RGB")
    fmt = (img.format or "JPEG").upper()

    if fmt in ("PNG", "WEBP"):

        buffer_jpeg = BytesIO()
        img_rgb.save(buffer_jpeg, format="JPEG", quality=75)
        buffer_jpeg.seek(0)
        img_base = Image.open(buffer_jpeg).convert("RGB")

        buffer2 = BytesIO()
        img_base.save(buffer2, format="JPEG", quality=quality)
        buffer2.seek(0)
        img_compressed = Image.open(buffer2).convert("RGB")

        diff = ImageChops.difference(img_base, img_compressed)
        amplifier = 1.2
    else:

        buffer = BytesIO()
        img_rgb.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        img_compressed = Image.open(buffer).convert("RGB")

        diff = ImageChops.difference(img_rgb, img_compressed)
        amplifier = 1.0

    diff_array = np.array(diff).astype(np.float32) * amplifier

    ela_visual = np.clip(diff_array * 10, 0, 255).astype(np.uint8)
    ela_pil = Image.fromarray(ela_visual)
    buffer_out = BytesIO()
    ela_pil.save(buffer_out, format="PNG")
    ela_b64 = base64.b64encode(buffer_out.getvalue()).decode("utf-8")

    return ela_b64


def preprocess_image(img: Image.Image) -> np.ndarray:

    img = img.convert("RGB").resize((224, 224))

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    img = Image.open(buffer).convert("RGB")

    img_array = np.array(img, dtype=np.float32)
    return np.expand_dims(img_array, axis=0)


def clasificar_prediccion(prediction: float) -> str:
    return "IA" if prediction >= DECISION_THRESHOLD else "REAL"


def calcular_confianza(prediction: float, clasificacion: str) -> float:
    if clasificacion == "IA":
        confianza = prediction * 100
    elif clasificacion == "REAL":
        confianza = (1 - prediction) * 100
    return round(min(max(confianza, 0.0), 100.0), 1)


def analyze_image(img: Image.Image) -> dict:

    if model is None:
        return {"error": "El modelo no está disponible."}

    try:
        ela_imagen = ela_analysis(img)

        img_array = preprocess_image(img)
        raw_prediction = float(model.predict(img_array, verbose=0)[0][0])
        prediction = float(np.clip(raw_prediction, 0.0, 1.0))
        classification = clasificar_prediccion(prediction)
        confidence = calcular_confianza(prediction, classification)
        probability_ai = round(prediction * 100, 1)

        return {
            "prediccion":       classification,
            "probabilidad_ia":  probability_ai,
            "confianza":        confidence,
            "umbral_ia":        round(DECISION_THRESHOLD * 100, 1),
            "ela_imagen":       ela_imagen,
        }

    except Exception as e:
        print(f"[ERROR] Fallo al analizar la imagen: {e}")
        return {"error": "No se pudo analizar la imagen. Intenta con otro archivo."}
