from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import os

def extraer_metadatos(imagen_path):
    """
    Extrae metadatos EXIF de una imagen.
    Devuelve un diccionario limpio, listo para enviar como JSON.
    """
    datos = {
        "nombre_archivo": os.path.basename(imagen_path),
        "tamano_bytes": os.path.getsize(imagen_path),
        "tiene_exif": False,
        "exif": {},
        "gps": None,
        "software": None,
        "fecha_captura": None,
        "camara": None,
    }

    try:
        img = Image.open(imagen_path)
        datos["formato"] = img.format
        datos["dimensiones"] = f"{img.width}x{img.height}"
        datos["modo_color"] = img.mode

        exif_raw = img._getexif()
        if not exif_raw:
            return datos

        datos["tiene_exif"] = True
        exif = {}
        gps_info = {}

        for tag_id, valor in exif_raw.items():
            tag = TAGS.get(tag_id, tag_id)

            if tag == "GPSInfo":
                for gps_tag_id, gps_valor in valor.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_valor
                continue

            # Evitar datos binarios largos (thumbnails, maker notes, etc.)
            if isinstance(valor, bytes):
                continue

            exif[tag] = valor

        datos["exif"] = exif
        datos["software"] = exif.get("Software")
        datos["fecha_captura"] = exif.get("DateTimeOriginal") or exif.get("DateTime")
        marca = exif.get("Make", "")
        modelo = exif.get("Model", "")
        datos["camara"] = f"{marca} {modelo}".strip() or None

        if gps_info:
            datos["gps"] = _convertir_gps(gps_info)

    except Exception as e:
        datos["error"] = f"No se pudieron leer metadatos: {str(e)}"

    return datos


def _convertir_gps(gps_info):
    """Convierte coordenadas GPS EXIF (grados/min/seg) a decimal."""
    def a_decimal(valor, ref):
        try:
            grados, minutos, segundos = valor
            decimal = grados + (minutos / 60.0) + (segundos / 3600.0)
            if ref in ["S", "W"]:
                decimal = -decimal
            return round(decimal, 6)
        except Exception:
            return None

    lat = gps_info.get("GPSLatitude")
    lat_ref = gps_info.get("GPSLatitudeRef")
    lon = gps_info.get("GPSLongitude")
    lon_ref = gps_info.get("GPSLongitudeRef")

    if lat and lon and lat_ref and lon_ref:
        return {
            "latitud": a_decimal(lat, lat_ref),
            "longitud": a_decimal(lon, lon_ref),
        }
    return None