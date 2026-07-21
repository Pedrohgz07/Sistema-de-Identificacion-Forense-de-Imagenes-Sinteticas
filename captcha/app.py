
import os
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory
from PIL import Image
from analyzer import analyze_image
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB máximo
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def verificar_turnstile(token: str, ip: str | None = None) -> bool:

    if not token:
        return False

    if not TURNSTILE_SECRET_KEY:
        print("[ERROR] TURNSTILE_SECRET_KEY no está configurada.")
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
        print(f"[ERROR] Fallo verificando Turnstile: {e}")
        return False


# ── Rutas ───────────────────────────────────────────────────────────────────

@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/analizar", methods=["POST"])
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
        img = Image.open(file.stream)
        resultado = analyze_image(img)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"error": f"Error al procesar la imagen: {str(e)}"}), 500


@app.route("/como-funciona")
def como_funciona():
    return render_template("como-funciona.html")


@app.route("/acerca")
def acerca():
    return render_template("acerca.html")

if __name__ == "__main__":
    app.run(debug=True) 
