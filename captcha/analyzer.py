import time
import numpy as np
from PIL import Image, ImageChops
import tensorflow as tf
from io import BytesIO
import base64

MODEL_PATH = "model/modelo_ai_vs_real.keras"

try:
    model = tf.keras.models.load_model(MODEL_PATH)
except Exception as e:
    model = None
    print(f"[ERROR] No se pudo cargar el modelo: {e}")

THRESHOLD = 0.60

ELA_THRESHOLDS = {
    "JPEG": 20.0,
    "PNG":  12.0,
    "WEBP": 14.0,
}


def ela_analysis(img: Image.Image, quality: int = 90) -> tuple[float, int, str]:

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
        anomaly_threshold = 15
        amplifier = 1.2
    else:

        buffer = BytesIO()
        img_rgb.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        img_compressed = Image.open(buffer).convert("RGB")

        diff = ImageChops.difference(img_rgb, img_compressed)
        anomaly_threshold = 25
        amplifier = 1.0

    diff_array = np.array(diff).astype(np.float32) * amplifier
    ela_score = float(np.mean(diff_array))
    anomaly_count = int(np.sum(diff_array > anomaly_threshold))

    ela_visual = np.clip(diff_array * 10, 0, 255).astype(np.uint8)
    ela_pil = Image.fromarray(ela_visual)
    buffer_out = BytesIO()
    ela_pil.save(buffer_out, format="PNG")
    ela_b64 = base64.b64encode(buffer_out.getvalue()).decode("utf-8")

    return round(ela_score, 2), anomaly_count, ela_b64


def preprocess_image(img: Image.Image) -> np.ndarray:

    img = img.convert("RGB").resize((224, 224))

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    img = Image.open(buffer).convert("RGB")

    img_array = np.array(img, dtype=np.float32)
    return np.expand_dims(img_array, axis=0)


def calcular_confianza(prediction: float, is_ai: bool) -> float:
   
    if is_ai:
        confianza = prediction * 100
    else:
        confianza = (1 - prediction) * 100

    return round(min(max(confianza, 0.0), 100.0), 1)


def nivel_de_confianza(confianza: float) -> str:

    if confianza >= 85:
        return "Alto"
    if confianza >= 60:
        return "Medio"
    return "Bajo"


def analyze_image(img: Image.Image, use_ela: bool = True) -> dict:

    if model is None:
        return {"error": "El modelo no está disponible."}

    start = time.time()

    try:
        ela_imagen = None
        ela_score = None
        anomaly_count = None

        if use_ela:
            ela_score, anomaly_count, ela_imagen = ela_analysis(img)

        img_array = preprocess_image(img)
        prediction = float(model.predict(img_array, verbose=0)[0][0])

        is_ai = prediction >= THRESHOLD
        confidence = calcular_confianza(prediction, is_ai)

        elapsed = round(time.time() - start, 2)

        result = {
            "prediccion":       "IA" if is_ai else "REAL",
            "confianza":        confidence,
            "nivel_confianza":  nivel_de_confianza(confidence),
            "prediccion_cruda": round(prediction, 4),
            "tiempo":           elapsed,
            "ela_imagen":       ela_imagen,
        }

        if ela_score is not None:
            fmt = (img.format or "JPEG").upper()
            result["ela_score"]      = ela_score
            result["ela_anomalias"]  = anomaly_count
            result["ela_umbral_ref"] = ELA_THRESHOLDS.get(fmt, 20.0)

        return result

    except Exception as e:

        print(f"[ERROR] Fallo al analizar la imagen: {e}")
        return {"error": "No se pudo analizar la imagen. Intenta con otro archivo."}