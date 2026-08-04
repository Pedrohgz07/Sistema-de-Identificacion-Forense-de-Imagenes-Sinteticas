
import os
import logging
import warnings
import requests
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image, UnidentifiedImageError
from analyzer import analyze_image
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
logger = logging.getLogger(__name__)

RATE_LIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri=RATE_LIMIT_STORAGE_URI,
    headers_enabled=True,
)
limiter.exempt(app.view_functions["static"])

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 25_000_000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
USE_TURNSTILE_TEST_KEYS = os.environ.get(
    "TURNSTILE_USE_TEST_KEYS", ""
).lower() in {"1", "true", "yes"}
TURNSTILE_BYPASS_REQUESTED = os.environ.get(
    "TURNSTILE_BYPASS", ""
).lower() in {"1", "true", "yes"}
TURNSTILE_BYPASS = TURNSTILE_BYPASS_REQUESTED and FLASK_DEBUG
TURNSTILE_TEST_SITE_KEY = "1x00000000000000000000AA"
TURNSTILE_TEST_SECRET_KEY = "1x0000000000000000000000000000000AA"

TURNSTILE_SITE_KEY = (
    TURNSTILE_TEST_SITE_KEY
    if USE_TURNSTILE_TEST_KEYS
    else os.environ.get("TURNSTILE_SITE_KEY", "")
)
TURNSTILE_SECRET_KEY = (
    TURNSTILE_TEST_SECRET_KEY
    if USE_TURNSTILE_TEST_KEYS
    else os.environ.get("TURNSTILE_SECRET_KEY", "")
)
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

if TURNSTILE_BYPASS_REQUESTED and not FLASK_DEBUG:
    logger.error("Se ignoró TURNSTILE_BYPASS porque FLASK_DEBUG no está habilitado.")


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def abrir_imagen_segura(file_stream) -> Image.Image:
    file_stream.seek(0)

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(file_stream)
        width, height = image.size

        if (image.format or "").upper() not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("El contenido del archivo no corresponde a JPG, PNG o WEBP.")

        if width <= 0 or height <= 0:
            raise ValueError("La imagen tiene dimensiones inválidas.")
        if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
            raise ValueError(
                f"Las dimensiones máximas permitidas son "
                f"{MAX_IMAGE_WIDTH}×{MAX_IMAGE_HEIGHT} píxeles."
            )
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError(
                f"La imagen supera el máximo de {MAX_IMAGE_PIXELS:,} píxeles."
            )

        image.verify()

        file_stream.seek(0)
        image = Image.open(file_stream)
        image.load()
        return image


def verificar_turnstile(token: str, ip: str | None = None) -> bool:

    if TURNSTILE_BYPASS:
        return True

    if not token:
        return False

    if not TURNSTILE_SECRET_KEY:
        logger.error("TURNSTILE_SECRET_KEY no está configurada.")
        return False

    try:
        resp = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": ip,
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return bool(data.get("success", False))
    except (requests.RequestException, ValueError) as e:
        logger.warning("Fallo verificando Turnstile: %s", e)
        return False


@app.route("/")
def inicio():
    return render_template(
        "inicio.html",
        turnstile_site_key=TURNSTILE_SITE_KEY,
        turnstile_bypass=TURNSTILE_BYPASS,
    )


@app.route("/analizar", methods=["POST"])
@limiter.limit("5 per minute")
@limiter.limit("50 per hour")
def analizar():
    token = request.form.get("cf-turnstile-response", "")
    if not verificar_turnstile(token, request.remote_addr):
        return jsonify({"error": "Verificación de captcha fallida. Intenta de nuevo."}), 403

    if "imagen" not in request.files:
        return jsonify({"error": "No se recibió ninguna imagen"}), 400

    file = request.files["imagen"]

    if file.filename == "":
        return jsonify({"error": "Archivo vacío"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Formato no permitido. Usa JPG, PNG o WEBP"}), 400

    try:
        img = abrir_imagen_segura(file.stream)
        resultado = analyze_image(img)
        return jsonify(resultado)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return jsonify({"error": "La imagen contiene demasiados píxeles para procesarla de forma segura."}), 413
    except (UnidentifiedImageError, OSError, SyntaxError):
        return jsonify({"error": "El archivo no es una imagen válida o está dañado."}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Error inesperado procesando una imagen")
        return jsonify({"error": f"Error al procesar la imagen: {str(e)}"}), 500


@app.errorhandler(429)
def limite_solicitudes_excedido(error):
    return jsonify({
        "error": "Has realizado demasiadas solicitudes. Espera un momento antes de intentarlo de nuevo."
    }), 429


@app.route("/como-funciona")
def como_funciona():
    return render_template("como-funciona.html")


@app.route("/acerca")
def acerca():
    return render_template("acerca.html")

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG)
