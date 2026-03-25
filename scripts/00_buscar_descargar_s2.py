"""
=============================================================
PROYECTO: Cartografía Geoespacial Abierta — Ecuador
MÓDULO:   00 — Búsqueda y descarga Sentinel-2 via CDSE
ÁREA:     Parque Nacional Podocarpus
AUTOR:    Daniel Estrada | daniel.geo.consultor@proton.me
FECHA:    2026
=============================================================

DESCRIPCIÓN:
    Busca imágenes S2 L2A en el Copernicus Data Space Ecosystem
    (CDSE) y las descarga con barra de progreso, reanudación
    automática y manejo de errores robusto.

ANTES DE EJECUTAR:
    1. Crea el archivo .env en la carpeta del script con:

         CDSE_USER=tu_email@ejemplo.com
         CDSE_PASS=tu_contraseña

    2. Asegúrate de que .env esté en tu .gitignore:
         echo ".env" >> ../.gitignore

    3. Instala dependencias:
         pip install requests tqdm python-dotenv

CÓMO CORRER (CMD / Git Bash):
    cd /f/geodatos-ecuador/scripts
    python 00_buscar_descargar_s2.py

    Para descarga automática del mejor resultado:
    python 00_buscar_descargar_s2.py --descargar

    Para listar sin descargar (modo seguro por defecto):
    python 00_buscar_descargar_s2.py

TILES QUE CUBREN PODOCARPUS:
    - 17MPN → sector norte (Loja, Vilcabamba)
    - 17MPM → sector sur  (Zamora Chinchipe)
    Verifica cuál necesitas en: https://tileviewer.sentinel-hub.com/

ESTRUCTURA DE SALIDA:
    datos/raw/
    └── S2A_MSIL2A_YYYYMMDD_*.SAFE.zip   (~800 MB – 1.2 GB)
        ↑ descomprimir con: unzip *.zip -d ../datos/raw/
=============================================================
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Dependencias opcionales con mensaje de instalación claro
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("  ERROR: falta 'requests'  →  pip install requests")
    sys.exit(1)

try:
    from tqdm import tqdm
    TQDM = True
except ImportError:
    TQDM = False

try:
    from dotenv import load_dotenv
    load_dotenv()          # carga el .env del directorio actual
    DOTENV = True
except ImportError:
    DOTENV = False


# ============================================================
# CONFIGURACIÓN — edita este bloque si necesitas ajustar algo
# ============================================================

CONFIG = {
    # --- Área de búsqueda (bounding box del PN Podocarpus completo) ---
    # lon_min, lat_min, lon_max, lat_max  (WGS84)
    # Ajusta para buscar sólo el tile norte (17MPN) o sur (17MPM)
    "bbox": (-79.35, -4.65, -78.85, -3.95),

    # --- Período de búsqueda ---
    "fecha_inicio": "2024-06-01",   # Época seca recomendada: junio–septiembre
    "fecha_fin":    "2024-09-30",

    # --- Filtros ---
    "nubosidad_max":  20,           # % máximo de cobertura nubosa
    "nivel":          "S2MSI2A",    # L2A = reflectancia BOA, ya corregida
    "max_resultados": 20,

    # --- Descarga ---
    "output_dir":  Path("../datos/raw"),
    "chunk_size":  1024 * 1024,     # 1 MB por chunk (ajustar si la red es lenta)
}

# Endpoints CDSE (actualizados 2025)
CDSE_AUTH_URL    = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
CDSE_DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products({id})/$value"

# URL del browser para descarga manual (se rellena automáticamente)
BROWSER_BASE = "https://browser.dataspace.copernicus.eu/?zoom=9&lat=-4.3&lng=-79.1"


# ============================================================
# FUNCIONES DE AUTENTICACIÓN
# ============================================================

def cargar_credenciales() -> tuple[str, str]:
    """
    Lee usuario/contraseña desde .env o variables de entorno.
    Nunca las hardcodees en el script — así no suben a GitHub.

    Crea un archivo .env junto a este script con:
        CDSE_USER=tu_email@ejemplo.com
        CDSE_PASS=tu_contraseña
    """
    usuario  = os.getenv("CDSE_USER", "")
    password = os.getenv("CDSE_PASS", "")

    if not usuario or not password:
        print("\n  ERROR: No se encontraron credenciales CDSE.")
        print("\n  Crea el archivo .env en la carpeta scripts/ con:")
        print("  ─────────────────────────────────────────")
        print("  CDSE_USER=tu_email@ejemplo.com")
        print("  CDSE_PASS=tu_contraseña")
        print("  ─────────────────────────────────────────")
        print("\n  Y asegúrate de que .env está en tu .gitignore:")
        print("  echo \".env\" >> ../.gitignore")
        print("\n  Crea cuenta gratis en: https://dataspace.copernicus.eu/")
        sys.exit(1)

    return usuario, password


def obtener_token(usuario: str, password: str) -> str:
    """
    Obtiene token JWT de acceso via OAuth2.
    Los tokens CDSE expiran en ~10 minutos.
    """
    try:
        resp = requests.post(
            CDSE_AUTH_URL,
            data={
                "client_id":  "cdse-public",
                "grant_type": "password",
                "username":   usuario,
                "password":   password,
            },
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        print("\n  ERROR de conexión: verifica tu internet o el estado de CDSE:")
        print("  https://status.dataspace.copernicus.eu/")
        sys.exit(1)

    if resp.status_code == 401:
        print("\n  ERROR 401: credenciales incorrectas.")
        print("  Verifica usuario y contraseña en tu archivo .env")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"\n  ERROR {resp.status_code} en autenticación:")
        print(f"  {resp.text[:300]}")
        sys.exit(1)

    token = resp.json().get("access_token", "")
    if not token:
        print("\n  ERROR: el servidor no devolvió token. Intenta en unos minutos.")
        sys.exit(1)

    print("  ✓ Autenticado en Copernicus Data Space")
    return token


# ============================================================
# BÚSQUEDA EN CATÁLOGO
# ============================================================

def construir_filtro_odata(bbox: tuple, fecha_inicio: str, fecha_fin: str,
                            nivel: str, nubosidad_max: int) -> str:
    """
    Construye el filtro OData para la API de catálogo CDSE.
    La API de catálogo es pública — no requiere token para buscar.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    bbox_wkt = (
        f"POLYGON(({lon_min} {lat_min},"
        f"{lon_max} {lat_min},"
        f"{lon_max} {lat_max},"
        f"{lon_min} {lat_max},"
        f"{lon_min} {lat_min}))"
    )

    return (
        f"Collection/Name eq 'SENTINEL-2' "
        f"and Attributes/OData.CSC.StringAttribute/any("
        f"  att:att/Name eq 'productType' "
        f"  and att/OData.CSC.StringAttribute/Value eq '{nivel}') "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_wkt}') "
        f"and ContentDate/Start gt {fecha_inicio}T00:00:00.000Z "
        f"and ContentDate/Start lt {fecha_fin}T23:59:59.000Z "
        f"and Attributes/OData.CSC.DoubleAttribute/any("
        f"  att:att/Name eq 'cloudCover' "
        f"  and att/OData.CSC.DoubleAttribute/Value le {nubosidad_max})"
    )


def buscar_imagenes() -> list:
    """
    Busca imágenes S2 L2A disponibles. Ordena por nubosidad ascendente.
    No requiere token — el catálogo es acceso abierto.
    """
    filtro = construir_filtro_odata(
        bbox          = CONFIG["bbox"],
        fecha_inicio  = CONFIG["fecha_inicio"],
        fecha_fin     = CONFIG["fecha_fin"],
        nivel         = CONFIG["nivel"],
        nubosidad_max = CONFIG["nubosidad_max"],
    )

    params = {
        "$filter":  filtro,
        "$orderby": (
            "Attributes/OData.CSC.DoubleAttribute/any("
            "att:att/Name eq 'cloudCover' "
            "and att/OData.CSC.DoubleAttribute/Value) asc"
        ),
        "$top":     CONFIG["max_resultados"],
        "$expand":  "Attributes",
    }

    try:
        resp = requests.get(CDSE_CATALOG_URL, params=params, timeout=40)
    except requests.exceptions.ConnectionError:
        print("  ERROR de conexión al catálogo CDSE.")
        return []

    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code} en búsqueda: {resp.text[:200]}")
        return []

    return resp.json().get("value", [])


def extraer_metadatos(producto: dict) -> dict:
    """
    Extrae los campos clave de un producto del catálogo CDSE.
    """
    nombre = producto.get("Name", "")
    fecha  = producto.get("ContentDate", {}).get("Start", "")[:10]
    prod_id = producto.get("Id", "")

    nubosidad = None
    tamano_mb = None
    for attr in producto.get("Attributes", []):
        if attr.get("Name") == "cloudCover":
            nubosidad = round(float(attr.get("Value", 0)), 1)
        if attr.get("Name") == "size":
            tamano_mb = round(float(attr.get("Value", 0)) / 1e6, 0)

    # Extraer tile del nombre (ej: T17MPN)
    tile = ""
    partes = nombre.split("_")
    for p in partes:
        if p.startswith("T") and len(p) == 6:
            tile = p
            break

    return {
        "id":         prod_id,
        "nombre":     nombre,
        "fecha":      fecha,
        "nubosidad":  nubosidad,
        "tile":       tile,
        "tamano_mb":  tamano_mb,
    }


def mostrar_tabla(productos: list) -> None:
    """
    Imprime tabla formateada de resultados en terminal.
    """
    if not productos:
        print("\n  Sin resultados. Sugerencias:")
        print("  · Amplía el rango de fechas en CONFIG")
        print("  · Aumenta nubosidad_max a 30 o 40%")
        print("  · Verifica el bbox en: https://tileviewer.sentinel-hub.com/")
        return

    print(f"\n  {'#':<4} {'TILE':<8} {'FECHA':<12} {'NUBES':>7}  {'NOMBRE (recortado)'}")
    print("  " + "─" * 90)

    for i, prod in enumerate(productos):
        meta = extraer_metadatos(prod)
        nubes = f"{meta['nubosidad']}%" if meta['nubosidad'] is not None else " N/A"
        nombre_corto = meta["nombre"][:55] + "…" if len(meta["nombre"]) > 55 else meta["nombre"]
        print(f"  {i+1:<4} {meta['tile']:<8} {meta['fecha']:<12} {nubes:>7}  {nombre_corto}")

    print(f"\n  Total: {len(productos)} imágenes encontradas")
    print(f"  Período: {CONFIG['fecha_inicio']} → {CONFIG['fecha_fin']}")
    print(f"  Nubosidad ≤ {CONFIG['nubosidad_max']}%")


def generar_url_browser() -> str:
    """
    Genera la URL del Copernicus Browser con los filtros preconfigurados.
    Útil para descarga manual o para verificar visualmente las escenas.
    """
    lon_min, lat_min, lon_max, lat_max = CONFIG["bbox"]
    lat_c = (lat_min + lat_max) / 2
    lon_c = (lon_min + lon_max) / 2

    # El browser de Copernicus acepta parámetros en la URL
    url = (
        f"https://browser.dataspace.copernicus.eu/"
        f"?zoom=10&lat={lat_c:.3f}&lng={lon_c:.3f}"
        f"&datasetId=S2_L2A"
        f"&fromTime={CONFIG['fecha_inicio']}T00%3A00%3A00.000Z"
        f"&toTime={CONFIG['fecha_fin']}T23%3A59%3A59.999Z"
        f"&maxCloudCoverage={CONFIG['nubosidad_max']}"
    )
    return url


# ============================================================
# DESCARGA CON REANUDACIÓN
# ============================================================

def descargar_imagen(producto: dict, token: str) -> Path | None:
    """
    Descarga una imagen S2 con:
    - Barra de progreso (tqdm si está instalado)
    - Reanudación automática si el archivo parcial existe
    - Indicador de velocidad y tiempo estimado
    - Manejo de error de token expirado
    """
    meta = extraer_metadatos(producto)
    output_dir = CONFIG["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    nombre_zip = meta["nombre"] + ".zip"
    dest       = output_dir / nombre_zip
    url        = CDSE_DOWNLOAD_URL.format(id=meta["id"])
    headers    = {"Authorization": f"Bearer {token}"}

    # Verificar si ya está descargado completamente
    if dest.exists():
        # Comprobación básica: si pesa más de 500 MB, asumir que está bien
        if dest.stat().st_size > 500 * 1024 * 1024:
            print(f"\n  ✓ Ya existe: {nombre_zip}")
            print(f"    ({dest.stat().st_size / 1e9:.2f} GB)")
            return dest
        else:
            print(f"\n  Archivo parcial detectado: {nombre_zip}")
            print(f"    ({dest.stat().st_size / 1e6:.0f} MB descargados)")

    # Verificar tamaño ya descargado para reanudación
    descargado = dest.stat().st_size if dest.exists() else 0
    if descargado > 0:
        headers["Range"] = f"bytes={descargado}-"
        print(f"  Reanudando desde {descargado / 1e6:.0f} MB...")
        modo_archivo = "ab"  # append binary
    else:
        modo_archivo = "wb"

    print(f"\n  Descargando: {nombre_zip}")
    print(f"  Destino: {dest.resolve()}")

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=120)
    except requests.exceptions.ConnectionError:
        print("  ERROR de conexión durante la descarga. Intenta de nuevo.")
        return None

    # Token expirado (ocurre en descargas largas > 10 min)
    if resp.status_code == 401:
        print("  ERROR 401: token expirado. Re-autenticando...")
        return None  # el caller deberá pedir nuevo token

    if resp.status_code not in (200, 206):
        print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
        return None

    total_remoto = int(resp.headers.get("content-length", 0))
    total_total  = descargado + total_remoto

    inicio = time.time()

    if TQDM and total_total > 0:
        with tqdm(
            total=total_total,
            initial=descargado,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"  {meta['tile']}",
            ncols=80,
        ) as pbar:
            with open(dest, modo_archivo) as f:
                for chunk in resp.iter_content(chunk_size=CONFIG["chunk_size"]):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
    else:
        # Fallback sin tqdm
        acumulado = descargado
        with open(dest, modo_archivo) as f:
            for chunk in resp.iter_content(chunk_size=CONFIG["chunk_size"]):
                if chunk:
                    f.write(chunk)
                    acumulado += len(chunk)
                    if total_total > 0:
                        pct      = acumulado / total_total * 100
                        elapsed  = time.time() - inicio
                        speed_mb = (acumulado - descargado) / max(elapsed, 0.1) / 1e6
                        print(f"\r  {pct:.1f}%  |  {acumulado/1e9:.2f} GB  |  {speed_mb:.1f} MB/s", end="", flush=True)
        print()

    elapsed = time.time() - inicio
    size_gb = dest.stat().st_size / 1e9
    print(f"\n  ✓ Descarga completa en {elapsed/60:.1f} min")
    print(f"    Tamaño: {size_gb:.2f} GB → {dest.name}")
    return dest


def descomprimir_zip(zip_path: Path) -> Path | None:
    """
    Descomprime el .zip en la misma carpeta.
    Requiere 'unzip' disponible en PATH (incluido en Git Bash).
    """
    import subprocess
    output_dir = zip_path.parent

    print(f"\n  Descomprimiendo {zip_path.name}...")
    resultado = subprocess.run(
        ["unzip", "-n", str(zip_path), "-d", str(output_dir)],
        capture_output=True, text=True
    )

    if resultado.returncode == 0:
        # Encontrar la carpeta .SAFE generada
        safe_dirs = list(output_dir.glob("*.SAFE"))
        if safe_dirs:
            print(f"  ✓ Listo: {safe_dirs[0].name}")
            return safe_dirs[0]
    else:
        print(f"  ERROR al descomprimir: {resultado.stderr[:200]}")
        print(f"  Descomprime manualmente con:")
        print(f"  unzip \"{zip_path.name}\" -d \"{output_dir}\"")

    return None


# ============================================================
# FLUJO PRINCIPAL
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Busca y descarga imágenes Sentinel-2 L2A del PN Podocarpus"
    )
    parser.add_argument(
        "--descargar", "-d",
        action="store_true",
        help="Descarga automáticamente la imagen con menor nubosidad"
    )
    parser.add_argument(
        "--tile", "-t",
        choices=["17MPN", "17MPM", "ambos"],
        default="ambos",
        help="Tile específico a buscar (17MPN=norte/Loja, 17MPM=sur/Zamora)"
    )
    parser.add_argument(
        "--descomprimir",
        action="store_true",
        help="Descomprime el .zip tras la descarga"
    )
    args = parser.parse_args()

    print("=" * 62)
    print("  BÚSQUEDA SENTINEL-2 L2A — PN PODOCARPUS")
    print("=" * 62)

    # --- Cargar credenciales ---
    print("\n[1/4] Cargando credenciales desde .env...")
    usuario, password = cargar_credenciales()
    print(f"  Usuario: {usuario[:4]}{'*' * (len(usuario) - 8)}{usuario[-4:]}")

    # --- Autenticar ---
    print("\n[2/4] Autenticando en Copernicus Data Space...")
    token = obtener_token(usuario, password)

    # --- Buscar imágenes ---
    print(f"\n[3/4] Buscando imágenes disponibles...")
    print(f"  Período:    {CONFIG['fecha_inicio']} → {CONFIG['fecha_fin']}")
    print(f"  Nubosidad:  ≤ {CONFIG['nubosidad_max']}%")
    print(f"  Nivel:      Sentinel-2 L2A (reflectancia BOA)")

    productos = buscar_imagenes()

    # Filtrar por tile si se especificó
    if args.tile != "ambos":
        productos = [p for p in productos
                     if args.tile in p.get("Name", "")]
        print(f"  Filtro tile: {args.tile}")

    mostrar_tabla(productos)

    # --- URL para browser manual ---
    url_browser = generar_url_browser()
    print(f"\n  Para ver en browser (descarga manual):")
    print(f"  {url_browser}")

    # --- Descarga ---
    print(f"\n[4/4] {'Descargando...' if args.descargar else 'Modo listado (sin descarga)'}")

    if not args.descargar:
        print("\n  Para descargar automáticamente el mejor resultado:")
        print("  python 00_buscar_descargar_s2.py --descargar")
        print("\n  Para un tile específico:")
        print("  python 00_buscar_descargar_s2.py --descargar --tile 17MPN")
        print("\n  Tras la descarga, ejecuta:")
        print("  python 01_preprocesar_sentinel2.py")

    elif not productos:
        print("\n  No hay imágenes para descargar.")
        print("  Revisa los filtros en CONFIG o usa el browser:")
        print(f"  {url_browser}")

    else:
        mejor = productos[0]
        meta  = extraer_metadatos(mejor)
        print(f"\n  Seleccionado: {meta['nombre'][:60]}…")
        print(f"  Tile: {meta['tile']}  |  Nubes: {meta['nubosidad']}%  |  Fecha: {meta['fecha']}")

        zip_path = descargar_imagen(mejor, token)

        if zip_path is None:
            # Intento de re-autenticación por token expirado
            print("  Renovando token...")
            token    = obtener_token(usuario, password)
            zip_path = descargar_imagen(mejor, token)

        if zip_path and args.descomprimir:
            safe_dir = descomprimir_zip(zip_path)
            if safe_dir:
                print(f"\n  ✓ Imagen lista en: {safe_dir}")
                print(f"  Actualiza CONFIG en 01_preprocesar_sentinel2.py:")
                print(f"    \"safe_dir\": Path(\"{safe_dir.resolve()}\"),")

        elif zip_path:
            print(f"\n  Para descomprimir manualmente (Git Bash):")
            print(f"  cd ../datos/raw")
            print(f"  unzip {zip_path.name}")

    # --- Resumen final ---
    print("\n" + "=" * 62)
    print("  PRÓXIMO PASO")
    print("=" * 62)
    print("  1. Verifica la imagen en QGIS (color natural)")
    print("  2. Edita CONFIG en 01_preprocesar_sentinel2.py")
    print("  3. Ejecuta: python 01_preprocesar_sentinel2.py")
    print()


if __name__ == "__main__":
    main()
