"""
=============================================================
PROYECTO: Cartografía Geoespacial Abierta — Ecuador
MÓDULO:   01 — Preprocesamiento Sentinel-2 (L2A)
ÁREA:     Parque Nacional Podocarpus
AUTOR:    Daniel Estrada | daniel.geo.consultor@proton.me
FECHA:    2026
=============================================================

DESCRIPCIÓN:
    Preprocesa imágenes Sentinel-2 Level-2A (ya corregidas
    atmosféricamente por ESA). Recorta al AOI de Podocarpus,
    apila bandas seleccionadas, calcula índices espectrales
    (NDVI, EVI, NDWI, BSI) y exporta GeoTIFFs listos para
    clasificación en QGIS.

DATOS REQUERIDOS:
    - Imágenes S2 L2A descargadas de Copernicus Browser
      (https://browser.dataspace.copernicus.eu)
    - Shapefile del límite del PN Podocarpus (SNAPEcuador)
    - DEM Copernicus 30m (opcional, para corrección topográfica)

ESTRUCTURA DE CARPETAS ESPERADA:
    proyecto/
    ├── datos/
    │   ├── raw/
    │   │   └── S2A_MSIL2A_20240101T.../   ← carpeta .SAFE
    │   ├── aoi/
    │   │   └── podocarpus_limite.shp
    │   └── procesados/
    ├── scripts/
    └── resultados/

DEPENDENCIAS:
    pip install rasterio numpy geopandas shapely matplotlib
                fiona pyproj scipy
=============================================================
"""

import os
import sys
import json
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.enums import Resampling as ResamplingEnum
import geopandas as gpd
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURACIÓN — edita estas rutas antes de ejecutar
# ============================================================

CONFIG = {
    # Ruta base del proyecto (donde están datos/, scripts/, etc.)
    "proyecto_dir": Path("../"),

    # Carpeta con la imagen .SAFE descargada de Copernicus
    # Ejemplo: "S2A_MSIL2A_20240315T152641_N0510_R025_T17MQN_20240315T213456.SAFE"
    "safe_dir": Path("../datos/raw/TU_IMAGEN.SAFE"),

    # Shapefile del límite del parque (en cualquier CRS, se reprojecta automático)
    "aoi_shp": Path("../datos/aoi/podocarpus_limite.shp"),

    # Carpeta de salida
    "output_dir": Path("../datos/procesados"),

    # Resolución de trabajo en metros (10 = alta, 20 = media, 60 = baja)
    # Para clasificación de cobertura vegetal usa 10m
    "resolucion": 10,

    # Nombre del proyecto para los archivos de salida
    "nombre_proyecto": "podocarpus_2024",
}

# Bandas S2 a procesar según resolución
# L2A: las bandas BOA ya están corregidas atmosféricamente
BANDAS_S2 = {
    10: {
        "B02": "azul",       # 490 nm
        "B03": "verde",      # 560 nm
        "B04": "rojo",       # 665 nm
        "B08": "nir",        # 842 nm
    },
    20: {
        "B05": "re1",        # 705 nm  Red Edge 1
        "B06": "re2",        # 740 nm  Red Edge 2
        "B07": "re3",        # 783 nm  Red Edge 3
        "B8A": "nir2",       # 865 nm  NIR estrecho
        "B11": "swir1",      # 1610 nm
        "B12": "swir2",      # 2190 nm
    },
    60: {
        "B01": "aerosol",    # 443 nm
        "B09": "vapor",      # 945 nm
    }
}


# ============================================================
# FUNCIONES PRINCIPALES
# ============================================================

def encontrar_bandas_safe(safe_dir: Path, resolucion: int) -> dict:
    """
    Busca los archivos JP2 de las bandas dentro del directorio .SAFE.
    Estructura interna de S2 L2A:
      .SAFE/GRANULE/*/IMG_DATA/R{res}m/T*_B{XX}_{res}m.jp2
    """
    safe_dir = Path(safe_dir)
    res_str = f"R{resolucion}m"
    bandas_encontradas = {}

    # Todas las bandas a buscar (res objetivo + 10m para NDVI)
    todas_bandas = {}
    todas_bandas.update(BANDAS_S2.get(10, {}))
    todas_bandas.update(BANDAS_S2.get(resolucion, {}))

    img_data = list(safe_dir.glob(f"GRANULE/*/IMG_DATA/{res_str}/*.jp2"))

    # Si no hay carpeta de la resolución exacta, buscar en R10m
    if not img_data:
        img_data = list(safe_dir.glob(f"GRANULE/*/IMG_DATA/R10m/*.jp2"))

    for jp2_path in img_data:
        nombre = jp2_path.stem  # ej: T17MQN_20240315T152641_B04_10m
        for banda_id in todas_bandas:
            if f"_{banda_id}_" in nombre or nombre.endswith(f"_{banda_id}"):
                bandas_encontradas[banda_id] = jp2_path

    if not bandas_encontradas:
        print(f"  ADVERTENCIA: No se encontraron bandas en {safe_dir}")
        print(f"  Verifica que la imagen sea S2 L2A y la ruta sea correcta.")

    return bandas_encontradas


def cargar_aoi(shp_path: Path, crs_target: str = "EPSG:32717") -> list:
    """
    Carga el shapefile del AOI y lo reprojecta al CRS de la imagen.
    Ecuador zona 17S → EPSG:32717
    Ecuador zona 18S → EPSG:32718
    Verifica cuál aplica según la cobertura de tu imagen.
    """
    gdf = gpd.read_file(shp_path)

    if gdf.crs is None:
        print("  ADVERTENCIA: El shapefile no tiene CRS definido. Asumiendo WGS84.")
        gdf = gdf.set_crs("EPSG:4326")

    gdf_proj = gdf.to_crs(crs_target)
    geometrias = [feat["geometry"] for feat in gdf_proj.__geo_interface__["features"]]
    return geometrias


def recortar_banda(ruta_banda: Path, geometrias: list, output_path: Path) -> dict:
    """
    Recorta una banda al AOI y guarda como GeoTIFF.
    Retorna metadata del archivo recortado.
    """
    with rasterio.open(ruta_banda) as src:
        # Reproyectar geometría al CRS de la imagen si es necesario
        out_image, out_transform = mask(src, geometrias, crop=True, nodata=0)
        out_meta = src.meta.copy()

    out_meta.update({
        "driver":    "GTiff",
        "height":    out_image.shape[1],
        "width":     out_image.shape[2],
        "transform": out_transform,
        "nodata":    0,
        "compress":  "lzw",
        "dtype":     "uint16",
    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(out_image)

    return out_meta


def apilar_bandas(rutas_bandas: dict, output_path: Path, orden_bandas: list = None) -> Path:
    """
    Apila múltiples bandas en un solo GeoTIFF multibanda.
    orden_bandas: lista de claves en el orden deseado para el stack.
    Orden recomendado para composición color natural: [B04, B03, B02]
    Orden recomendado para falso color: [B08, B04, B03]
    """
    if orden_bandas is None:
        orden_bandas = list(rutas_bandas.keys())

    # Leer primera banda para obtener metadata
    with rasterio.open(rutas_bandas[orden_bandas[0]]) as src:
        meta = src.meta.copy()
        meta.update(count=len(orden_bandas), compress="lzw")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        for i, banda_id in enumerate(orden_bandas, start=1):
            with rasterio.open(rutas_bandas[banda_id]) as src:
                dst.write(src.read(1), i)
            dst.set_band_description(i, banda_id)

    print(f"  Stack guardado: {output_path.name} ({len(orden_bandas)} bandas)")
    return output_path


def calcular_indice(array_a: np.ndarray, array_b: np.ndarray,
                    escala: float = 10000.0) -> np.ndarray:
    """
    Calcula índice normalizado genérico: (A - B) / (A + B)
    Los valores S2 L2A vienen en reflectancia × 10000, hay que normalizar.
    """
    a = array_a.astype(np.float32) / escala
    b = array_b.astype(np.float32) / escala

    with np.errstate(divide="ignore", invalid="ignore"):
        idx = np.where(
            (a + b) == 0,
            np.nan,
            (a - b) / (a + b)
        )
    return idx.astype(np.float32)


def calcular_evi(nir: np.ndarray, rojo: np.ndarray, azul: np.ndarray,
                 escala: float = 10000.0) -> np.ndarray:
    """
    EVI = 2.5 × (NIR - Rojo) / (NIR + 6×Rojo - 7.5×Azul + 1)
    Más sensible que NDVI en zonas de alta densidad vegetal (selva).
    """
    n = nir.astype(np.float32)   / escala
    r = rojo.astype(np.float32)  / escala
    a = azul.astype(np.float32)  / escala

    denom = n + 6 * r - 7.5 * a + 1
    with np.errstate(divide="ignore", invalid="ignore"):
        evi = np.where(denom == 0, np.nan, 2.5 * (n - r) / denom)
    return np.clip(evi, -1, 1).astype(np.float32)


def calcular_bsi(swir1: np.ndarray, rojo: np.ndarray,
                 nir: np.ndarray, azul: np.ndarray,
                 escala: float = 10000.0) -> np.ndarray:
    """
    BSI = ((SWIR1 + Rojo) - (NIR + Azul)) / ((SWIR1 + Rojo) + (NIR + Azul))
    Detecta suelo desnudo y zonas degradadas.
    Valores altos (>0.1) indican suelo expuesto.
    """
    s1 = swir1.astype(np.float32) / escala
    r  = rojo.astype(np.float32)  / escala
    n  = nir.astype(np.float32)   / escala
    a  = azul.astype(np.float32)  / escala

    num   = (s1 + r) - (n + a)
    denom = (s1 + r) + (n + a)
    with np.errstate(divide="ignore", invalid="ignore"):
        bsi = np.where(denom == 0, np.nan, num / denom)
    return bsi.astype(np.float32)


def guardar_indice(array: np.ndarray, referencia_path: Path,
                   output_path: Path, nombre: str) -> None:
    """
    Guarda un array de índice como GeoTIFF Float32.
    Usa la georeferencia de otro raster como referencia.
    Escala a Int16 (×10000) para ahorrar espacio sin perder precisión.
    """
    with rasterio.open(referencia_path) as src:
        meta = src.meta.copy()

    meta.update({
        "dtype":   "int16",
        "count":   1,
        "nodata":  -9999,
        "compress": "lzw",
    })

    # Escalar de float [-1,1] a int16 [-10000, 10000]
    array_scaled = np.where(
        np.isnan(array),
        -9999,
        (array * 10000).astype(np.int16)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(array_scaled, 1)

    # Calcular estadísticas básicas (ignorando nodata)
    vals = array[~np.isnan(array)]
    if len(vals) > 0:
        print(f"  {nombre}: min={vals.min():.3f} | "
              f"media={vals.mean():.3f} | max={vals.max():.3f}")


def generar_reporte(output_dir: Path, nombre_proyecto: str,
                    bandas_generadas: dict, indices_generados: list) -> None:
    """
    Genera un archivo JSON con el reporte del procesamiento.
    Útil para el README del repositorio GitHub.
    """
    reporte = {
        "proyecto": nombre_proyecto,
        "sensor":   "Sentinel-2 L2A",
        "area":     "Parque Nacional Podocarpus, Ecuador",
        "bandas_procesadas": list(bandas_generadas.keys()),
        "indices_calculados": indices_generados,
        "sistema_coordenadas": "EPSG:32717 (WGS84 / UTM Zone 17S)",
        "resolucion_m": CONFIG["resolucion"],
        "nota": "Reflectancia BOA ya corregida atmosféricamente por ESA (L2A).",
        "fuente_datos": "Copernicus Browser — https://browser.dataspace.copernicus.eu",
        "licencia_datos": "Copernicus Open Access — libre uso con atribución",
        "licencia_codigo": "MIT",
    }

    ruta_json = output_dir / f"{nombre_proyecto}_reporte.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)

    print(f"\n  Reporte guardado: {ruta_json.name}")


# ============================================================
# FLUJO PRINCIPAL
# ============================================================

def main():
    print("=" * 60)
    print(" PREPROCESAMIENTO SENTINEL-2 — PODOCARPUS")
    print("=" * 60)

    output_dir  = CONFIG["output_dir"]
    nombre      = CONFIG["nombre_proyecto"]
    resolucion  = CONFIG["resolucion"]
    safe_dir    = CONFIG["safe_dir"]
    aoi_shp     = CONFIG["aoi_shp"]

    output_dir.mkdir(parents=True, exist_ok=True)
    dir_bandas  = output_dir / "bandas"
    dir_indices = output_dir / "indices"
    dir_stacks  = output_dir / "stacks"

    # --- 1. Encontrar bandas en el .SAFE ---
    print("\n[1/5] Buscando bandas en archivo .SAFE...")
    bandas_paths = encontrar_bandas_safe(safe_dir, resolucion)

    if not bandas_paths:
        print("\n  ERROR: No se encontraron bandas.")
        print("  Verifica que safe_dir apunte a una carpeta .SAFE válida.")
        sys.exit(1)

    print(f"  Encontradas: {list(bandas_paths.keys())}")

    # --- 2. Cargar AOI ---
    print("\n[2/5] Cargando límite del AOI...")
    try:
        geometrias = cargar_aoi(aoi_shp)
        print(f"  AOI cargado: {aoi_shp.name}")
    except Exception as e:
        print(f"\n  ERROR cargando AOI: {e}")
        print("  Descarga el shapefile del PN Podocarpus de SNAPEcuador:")
        print("  https://geodata.environment.ec/")
        sys.exit(1)

    # --- 3. Recortar bandas al AOI ---
    print("\n[3/5] Recortando bandas al AOI...")
    bandas_recortadas = {}
    for banda_id, ruta_orig in bandas_paths.items():
        output_path = dir_bandas / f"{nombre}_{banda_id}.tif"
        print(f"  Procesando {banda_id}...", end=" ")
        try:
            recortar_banda(ruta_orig, geometrias, output_path)
            bandas_recortadas[banda_id] = output_path
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")

    # --- 4. Calcular índices espectrales ---
    print("\n[4/5] Calculando índices espectrales...")
    indices_generados = []

    def leer_banda(banda_id):
        with rasterio.open(bandas_recortadas[banda_id]) as src:
            return src.read(1).astype(np.float32)

    # NDVI — Índice de Vegetación de Diferencia Normalizada
    if "B08" in bandas_recortadas and "B04" in bandas_recortadas:
        print("  Calculando NDVI...", end=" ")
        ndvi = calcular_indice(leer_banda("B08"), leer_banda("B04"))
        guardar_indice(ndvi, bandas_recortadas["B04"],
                       dir_indices / f"{nombre}_NDVI.tif", "NDVI")
        indices_generados.append("NDVI")

    # EVI — Índice de Vegetación Mejorado
    if all(b in bandas_recortadas for b in ["B08", "B04", "B02"]):
        print("  Calculando EVI...", end=" ")
        evi = calcular_evi(leer_banda("B08"), leer_banda("B04"), leer_banda("B02"))
        guardar_indice(evi, bandas_recortadas["B04"],
                       dir_indices / f"{nombre}_EVI.tif", "EVI")
        indices_generados.append("EVI")

    # NDWI — Índice de Agua (Gao 1996, usando NIR y SWIR1)
    if "B08" in bandas_recortadas and "B11" in bandas_recortadas:
        print("  Calculando NDWI...", end=" ")
        ndwi = calcular_indice(leer_banda("B08"), leer_banda("B11"))
        guardar_indice(ndwi, bandas_recortadas["B08"],
                       dir_indices / f"{nombre}_NDWI.tif", "NDWI")
        indices_generados.append("NDWI")

    # BSI — Índice de Suelo Desnudo
    if all(b in bandas_recortadas for b in ["B11", "B04", "B08", "B02"]):
        print("  Calculando BSI...", end=" ")
        bsi = calcular_bsi(leer_banda("B11"), leer_banda("B04"),
                           leer_banda("B08"), leer_banda("B02"))
        guardar_indice(bsi, bandas_recortadas["B04"],
                       dir_indices / f"{nombre}_BSI.tif", "BSI")
        indices_generados.append("BSI")

    # --- 5. Crear stacks para composiciones ---
    print("\n[5/5] Generando stacks de composición...")

    # Color natural: B04-B03-B02 (Rojo-Verde-Azul)
    bandas_cn = [b for b in ["B04", "B03", "B02"] if b in bandas_recortadas]
    if len(bandas_cn) == 3:
        apilar_bandas(
            bandas_recortadas, dir_stacks / f"{nombre}_color_natural.tif",
            orden_bandas=bandas_cn
        )

    # Falso color infrarrojo: B08-B04-B03 (NIR-Rojo-Verde)
    # Vegetación sana aparece en rojo brillante
    bandas_fc = [b for b in ["B08", "B04", "B03"] if b in bandas_recortadas]
    if len(bandas_fc) == 3:
        apilar_bandas(
            bandas_recortadas, dir_stacks / f"{nombre}_falso_color_nir.tif",
            orden_bandas=bandas_fc
        )

    # Composición para análisis de vegetación: B11-B08-B04 (SWIR-NIR-Rojo)
    # Permite distinguir bosque, pastizal, suelo desnudo, agua
    bandas_veg = [b for b in ["B11", "B08", "B04"] if b in bandas_recortadas]
    if len(bandas_veg) == 3:
        apilar_bandas(
            bandas_recortadas, dir_stacks / f"{nombre}_composicion_veg.tif",
            orden_bandas=bandas_veg
        )

    # --- Reporte final ---
    generar_reporte(output_dir, nombre, bandas_recortadas, indices_generados)

    print("\n" + "=" * 60)
    print(" PREPROCESAMIENTO COMPLETADO")
    print("=" * 60)
    print(f"\n Archivos generados en: {output_dir.resolve()}")
    print(f"   bandas/    → {len(bandas_recortadas)} bandas recortadas (.tif)")
    print(f"   indices/   → {len(indices_generados)} índices espectrales")
    print(f"   stacks/    → composiciones multibanda")
    print("\n Próximo paso:")
    print("   Abre QGIS → Cargar stacks → Clasificar con SCP Plugin")
    print("   Recomendado: Script 02_clasificar_cobertura.py")


if __name__ == "__main__":
    main()
