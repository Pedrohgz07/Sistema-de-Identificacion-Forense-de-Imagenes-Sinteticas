
import os
import logging
import requests
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image, UnidentifiedImageError
from analyzer import analyze_image
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

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

Image.MAX_IMAGE_PIXELS = None

FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
USE_TURNSTILE_TEST_KEYS = os.environ.get(
    "TURNSTILE_USE_TEST_KEYS", ""
).lower() in {"1", "true", "yes"}
TURNSTILE_TEST_SITE_KEY = "1x00000000000000000000AA"
TURNSTILE_TEST_SECRET_KEY = "1x0000000000000000000000000000000AA"
TURNSTILE_SITE_KEY = (
    TURNSTILE_TEST_SITE_KEY
    if USE_TURNSTILE_TEST_KEYS
    else os.environ.get("TURNSTILE_SITE_KEY", "").strip()
)
TURNSTILE_SECRET_KEY = (
    TURNSTILE_TEST_SECRET_KEY
    if USE_TURNSTILE_TEST_KEYS
    else os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
)
TURNSTILE_EXPECTED_HOSTNAME = os.environ.get("TURNSTILE_EXPECTED_HOSTNAME", "").strip().lower()
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ACTION = "analyze-image"
TURNSTILE_TOKEN_MAX_LENGTH = 2048


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def abrir_imagen_segura(file_stream) -> Image.Image:
    file_stream.seek(0)
    image = Image.open(file_stream)
    width, height = image.size

    if (image.format or "").upper() not in ALLOWED_IMAGE_FORMATS:
        raise ValueError("El contenido del archivo no corresponde a JPG, PNG o WEBP.")

    if width <= 0 or height <= 0:
        raise ValueError("La imagen tiene dimensiones inválidas.")

    image.verify()

    file_stream.seek(0)
    image = Image.open(file_stream)
    image.load()
    return image


def verificar_turnstile(token: str, ip: str | None = None) -> bool:
    token = token.strip()
    if not token or len(token) > TURNSTILE_TOKEN_MAX_LENGTH:
        return False
    if not TURNSTILE_SECRET_KEY:
        logger.error("TURNSTILE_SECRET_KEY no está configurada.")
        return False

    payload = {"secret": TURNSTILE_SECRET_KEY, "response": token}
    if ip:
        payload["remoteip"] = ip

    try:
        response = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        response.raise_for_status()
        resultado = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("No se pudo validar Turnstile: %s", error)
        return False

    if not resultado.get("success"):
        logger.info("Turnstile rechazó el token: %s", resultado.get("error-codes", []))
        return False
    if not USE_TURNSTILE_TEST_KEYS and resultado.get("action") != TURNSTILE_ACTION:
        logger.warning("Acción de Turnstile inesperada: %r", resultado.get("action"))
        return False
    if not USE_TURNSTILE_TEST_KEYS and TURNSTILE_EXPECTED_HOSTNAME:
        hostname = str(resultado.get("hostname", "")).lower()
        if hostname != TURNSTILE_EXPECTED_HOSTNAME:
            logger.warning("Hostname de Turnstile inesperado: %r", hostname)
            return False
    return True


@app.route("/")
def inicio():
    return render_template("inicio.html", turnstile_site_key=TURNSTILE_SITE_KEY)


@app.route("/analizar", methods=["POST"])
@limiter.limit("5 per minute")
@limiter.limit("50 per hour")
def analizar():
    token = request.form.get("cf-turnstile-response", "")
    if not verificar_turnstile(token, request.remote_addr):
        return jsonify({"error": "No se pudo validar el CAPTCHA. Inténtalo de nuevo."}), 403

    if "imagen" not in request.files:
        return jsonify({"error": "No se recibió ninguna imagen."}), 400

    file = request.files["imagen"]

    if file.filename == "":
        return jsonify({"error": "El archivo está vacío."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Formato no permitido. Usa JPG, PNG o WEBP."}), 400

    try:
        img = abrir_imagen_segura(file.stream)
        resultado = analyze_image(img)
        return jsonify(resultado)
    except (UnidentifiedImageError, OSError, SyntaxError):
        return jsonify({"error": "El archivo no es una imagen válida o está dañado."}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        logger.exception("Error inesperado procesando una imagen")
        return jsonify({
            "error": "No se pudo procesar la imagen. Inténtalo de nuevo más tarde."
        }), 500


@app.errorhandler(413)
def archivo_demasiado_grande(error):
    return jsonify({
        "error": "La imagen supera el límite de 10 MB."
    }), 413


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


@app.route("/privacidad")
def privacidad():
    return render_template("privacidad.html")


@app.route("/documentacion")
def documentacion():
    return render_template("documentacion.html")

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG)
