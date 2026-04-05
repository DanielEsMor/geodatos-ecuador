#!/usr/bin/env python3
"""
03_buscar_y_descargar.py
Busca imágenes Sentinel-2 L2A (por tiles o polígono) y permite descargar las seleccionadas.
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from collections import defaultdict

import requests

try:
    from tqdm import tqdm
    TQDM = True
except ImportError:
    TQDM = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ========== CONFIGURACIÓN ==========
AREA_FILE_DEFAULT = Path("area.wkt")
CDSE_AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
CDSE_DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products({id})/$value"
OUTPUT_DIR = Path("../datos/raw")
CHUNK_SIZE = 1024 * 1024

# ========== FUNCIONES ==========
def cargar_poligono(archivo):
    with open(archivo, 'r') as f:
        wkt_str = f.read().strip().split('\n')[0]
    return wkt_str

def obtener_token(usuario, password):
    try:
        resp = requests.post(
            CDSE_AUTH_URL,
            data={
                "client_id": "cdse-public",
                "grant_type": "password",
                "username": usuario,
                "password": password,
            },
            timeout=30,
        )
    except Exception as e:
        print(f"  Error de conexión: {e}")
        return None
    if resp.status_code != 200:
        print(f"  Error autenticación: {resp.status_code}")
        return None
    return resp.json().get("access_token")

def extraer_tile(nombre):
    partes = nombre.split('_')
    for p in partes:
        if p.startswith('T') and len(p) >= 5:
            return p[:6]
    return "DESCONOCIDO"

def buscar_por_tiles(tiles, fecha_ini, fecha_fin, nubosidad_max, max_resultados, token):
    tile_condition = " or ".join([f"contains(Name,'{t}')" for t in tiles])
    filtro = (
        f"Collection/Name eq 'SENTINEL-2' "
        f"and Attributes/OData.CSC.StringAttribute/any(a: a/Name eq 'productType' and a/Value eq 'S2MSI2A') "
        f"and ContentDate/Start ge {fecha_ini}T00:00:00.000Z "
        f"and ContentDate/Start le {fecha_fin}T23:59:59.999Z "
        f"and ({tile_condition})"
    )
    params = {
        "$filter": filtro,
        "$top": max_resultados,
        "$orderby": "ContentDate/Start desc",
        "$expand": "Attributes",
    }
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.get(CDSE_CATALOG_URL, params=params, headers=headers, timeout=60)
    except Exception as e:
        print(f"  Error en la solicitud: {e}")
        return []
    if resp.status_code != 200:
        print(f"  Error {resp.status_code}: {resp.text[:200]}")
        return []
    productos = resp.json().get("value", [])
    filtrados = []
    for p in productos:
        nubes = None
        for attr in p.get("Attributes", []):
            if attr.get("Name") == "cloudCover":
                nubes = float(attr.get("Value", 100))
                break
        if nubes is not None and nubes <= nubosidad_max:
            nombre = p.get("Name", "")
            fecha = p.get("ContentDate", {}).get("Start", "")[:10]
            tile = extraer_tile(nombre)
            filtrados.append({
                "id": p.get("Id"),
                "nombre": nombre,
                "fecha": fecha,
                "nubosidad": nubes,
                "tile": tile,
            })
    filtrados.sort(key=lambda x: x["nubosidad"])
    return filtrados

def buscar_por_poligono(wkt, fecha_ini, fecha_fin, nubosidad_max, max_resultados, token):
    geometria = f"geography'SRID=4326;{wkt}'"
    filtro = (
        f"Collection/Name eq 'SENTINEL-2' "
        f"and Attributes/OData.CSC.StringAttribute/any(a: a/Name eq 'productType' and a/Value eq 'S2MSI2A') "
        f"and ContentDate/Start ge {fecha_ini}T00:00:00.000Z "
        f"and ContentDate/Start le {fecha_fin}T23:59:59.999Z "
        f"and OData.CSC.Intersects(area={geometria})"
    )
    params = {
        "$filter": filtro,
        "$top": max_resultados,
        "$orderby": "ContentDate/Start desc",
        "$expand": "Attributes",
    }
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.get(CDSE_CATALOG_URL, params=params, headers=headers, timeout=60)
    except Exception as e:
        print(f"  Error: {e}")
        return []
    if resp.status_code != 200:
        print(f"  Error {resp.status_code}: {resp.text[:200]}")
        return []
    productos = resp.json().get("value", [])
    filtrados = []
    for p in productos:
        nubes = None
        for attr in p.get("Attributes", []):
            if attr.get("Name") == "cloudCover":
                nubes = float(attr.get("Value", 100))
                break
        if nubes is not None and nubes <= nubosidad_max:
            nombre = p.get("Name", "")
            fecha = p.get("ContentDate", {}).get("Start", "")[:10]
            tile = extraer_tile(nombre)
            filtrados.append({
                "id": p.get("Id"),
                "nombre": nombre,
                "fecha": fecha,
                "nubosidad": nubes,
                "tile": tile,
            })
    filtrados.sort(key=lambda x: x["nubosidad"])
    return filtrados

def mostrar_resultados(imagenes):
    if not imagenes:
        print("\n  No se encontraron imágenes.")
        return []

    # Agrupar por tile
    por_tile = defaultdict(list)
    for img in imagenes:
        por_tile[img['tile']].append(img)

    print("\n  RESUMEN POR TILE:")
    print("  " + "-" * 50)
    for tile, lista in sorted(por_tile.items()):
        fechas = sorted([img['fecha'] for img in lista])
        print(f"  {tile}: {len(lista)} imágenes  (desde {fechas[0]} hasta {fechas[-1]})")
    print("  " + "-" * 50)

    print("\n  DETALLE POR TILE (para seleccionar):")
    global_idx = 1
    for tile, lista in sorted(por_tile.items()):
        print(f"\n  🗺️  TILE {tile}  ({len(lista)} imágenes)")
        print("  " + "-" * 70)
        lista_ordenada = sorted(lista, key=lambda x: x['nubosidad'])
        for i, img in enumerate(lista_ordenada, 1):
            nubes_str = f"{img['nubosidad']:.1f}%" if img['nubosidad'] is not None else "N/A"
            nombre_corto = img['nombre'][:50] + "…" if len(img['nombre']) > 50 else img['nombre']
            print(f"    [{global_idx:3d}] {img['fecha']} | {nubes_str:>6} | {nombre_corto}")
            # Guardar el índice global en el diccionario de la imagen para luego poder seleccionar
            img['global_index'] = global_idx
            global_idx += 1

    return imagenes  # ahora con el campo global_index

def parse_indices(indices_str, total):
    """Parsea una cadena como '1,3,5-8' y devuelve lista de enteros válidos."""
    indices = set()
    for part in indices_str.split(','):
        part = part.strip()
        if '-' in part:
            r = part.split('-')
            if len(r) == 2:
                try:
                    start = int(r[0])
                    end = int(r[1])
                    indices.update(range(start, end+1))
                except:
                    pass
        else:
            try:
                indices.add(int(part))
            except:
                pass
    # Filtrar los que están dentro del rango
    return [i for i in indices if 1 <= i <= total]

def descargar_imagen(imagen, token):
    """Descarga una imagen con barra de progreso y reanudación."""
    nombre = imagen['nombre']
    prod_id = imagen['id']
    fecha = imagen['fecha']
    nubes = imagen['nubosidad']
    tile = imagen['tile']

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    dest = output_dir / f"{nombre}.zip"
    url = CDSE_DOWNLOAD_URL.format(id=prod_id)
    headers = {"Authorization": f"Bearer {token}"}

    if dest.exists() and dest.stat().st_size > 500 * 1024 * 1024:
        print(f"  Ya existe: {dest.name}")
        return dest

    descargado = dest.stat().st_size if dest.exists() else 0
    if descargado > 0:
        headers["Range"] = f"bytes={descargado}-"
        modo = "ab"
        print(f"  Reanudando desde {descargado/1e6:.0f} MB...")
    else:
        modo = "wb"

    print(f"\n  📥 {fecha} | Nubes: {nubes}% | Tile: {tile}")
    print(f"     {nombre[:60]}...")

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=120)
    except Exception as e:
        print(f"  Error de conexión: {e}")
        return None

    if resp.status_code not in (200, 206):
        print(f"  Error {resp.status_code}")
        return None

    total = descargado + int(resp.headers.get("content-length", 0))
    inicio = time.time()

    with open(dest, modo) as f:
        if TQDM:
            with tqdm(total=total, initial=descargado, unit="B",
                      unit_scale=True, unit_divisor=1024,
                      desc="     ") as pbar:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        else:
            acum = descargado
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    acum += len(chunk)
                    print(f"\r    {acum/total*100:.1f}%", end="", flush=True)
            print()

    print(f"    ✅ Completo en {(time.time()-inicio)/60:.1f} min ({dest.stat().st_size/1e9:.2f} GB)")
    return dest

def cargar_credenciales():
    usuario = os.getenv("CDSE_USER", "")
    password = os.getenv("CDSE_PASS", "")
    if not usuario or not password:
        print("\n  ERROR: Credenciales no encontradas en .env")
        sys.exit(1)
    return usuario, password

# ========== MAIN ==========
def main():
    parser = argparse.ArgumentParser(
        description="Busca imágenes Sentinel-2 L2A y descarga las seleccionadas."
    )
    parser.add_argument("--tiles-file", help="Archivo con lista de tiles (uno por línea)")
    parser.add_argument("--tiles", help="Lista de tiles separados por coma, ej: T17MPQ,T17MPR")
    parser.add_argument("--area", help="Archivo WKT con el polígono (búsqueda geográfica)")
    parser.add_argument("--fecha-inicio", default="2024-07-01", help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--fecha-fin", default="2024-09-30", help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--nubes", type=int, default=30, help="Nubosidad máxima (porcentaje)")
    parser.add_argument("--max", type=int, default=200, help="Máximo número de resultados a mostrar")
    parser.add_argument("--indices", help="Descargar solo estos índices (ej: 1,3,5-8). Si no se da, se pregunta interactivamente.")
    parser.add_argument("--no-preguntar", action="store_true", help="No preguntar, usar --indices o descargar todos si no se especifica")
    args = parser.parse_args()

    print("=" * 70)
    print("  BÚSQUEDA Y DESCARGA DE IMÁGENES SENTINEL-2 L2A")
    print("=" * 70)

    # Autenticación
    print("\n[1/4] Autenticando...")
    usuario, password = cargar_credenciales()
    token = obtener_token(usuario, password)
    if not token:
        print("  Error de autenticación. Abortando.")
        sys.exit(1)
    print("  ✅ Autenticado")

    # Determinar método de búsqueda
    if args.tiles_file:
        try:
            with open(args.tiles_file, 'r') as f:
                tiles_list = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"  Error leyendo {args.tiles_file}: {e}")
            sys.exit(1)
        if not tiles_list:
            print("  El archivo de tiles está vacío.")
            sys.exit(1)
        print(f"\n[2/4] Buscando por tiles desde archivo: {args.tiles_file}")
        print(f"  Tiles: {', '.join(tiles_list)}")
        imagenes = buscar_por_tiles(
            tiles_list,
            args.fecha_inicio,
            args.fecha_fin,
            args.nubes,
            args.max,
            token
        )
    elif args.tiles:
        tiles_list = [t.strip() for t in args.tiles.split(',')]
        print(f"\n[2/4] Buscando por tiles: {', '.join(tiles_list)}")
        imagenes = buscar_por_tiles(
            tiles_list,
            args.fecha_inicio,
            args.fecha_fin,
            args.nubes,
            args.max,
            token
        )
    else:
        archivo_poly = args.area if args.area else AREA_FILE_DEFAULT
        print(f"\n[2/4] Buscando por polígono desde {archivo_poly}...")
        if not archivo_poly.exists():
            print("  ERROR: No existe el archivo de polígono.")
            sys.exit(1)
        wkt = cargar_poligono(archivo_poly)
        imagenes = buscar_por_poligono(
            wkt,
            args.fecha_inicio,
            args.fecha_fin,
            args.nubes,
            args.max,
            token
        )

    # Mostrar resultados
    print("\n[3/4] Resultados de la búsqueda:")
    imagenes_con_indices = mostrar_resultados(imagenes)
    if not imagenes_con_indices:
        print("  No hay imágenes para descargar.")
        return

    total_imagenes = len(imagenes_con_indices)

    # Seleccionar índices
    if args.indices:
        indices_seleccionados = parse_indices(args.indices, total_imagenes)
        if not indices_seleccionados:
            print(f"\n  No se encontraron índices válidos en '{args.indices}'. Abortando.")
            return
    elif args.no_preguntar:
        print("\n  --no-preguntar activado y no se dieron índices. Descargando todas las imágenes.")
        indices_seleccionados = list(range(1, total_imagenes + 1))
    else:
        print("\n[4/4] Selección de imágenes para descarga:")
        print("  Introduce los números de las imágenes que quieres descargar (ej: 1,3,5-8,12)")
        print("  También puedes escribir 'todos' o dejar en blanco para cancelar.")
        respuesta = input("  Números: ").strip()
        if respuesta.lower() in ['todos', 'all']:
            indices_seleccionados = list(range(1, total_imagenes + 1))
        elif respuesta == '':
            print("  Cancelado.")
            return
        else:
            indices_seleccionados = parse_indices(respuesta, total_imagenes)
            if not indices_seleccionados:
                print("  No se reconocieron números válidos. Cancelando.")
                return

    # Filtrar las imágenes seleccionadas
    seleccion = []
    for img in imagenes_con_indices:
        if img['global_index'] in indices_seleccionados:
            seleccion.append(img)

    if not seleccion:
        print("  No se seleccionó ninguna imagen.")
        return

    print(f"\n  Se descargarán {len(seleccion)} imágenes ({len(seleccion)*1.2:.1f} GB aprox.)")
    if not args.no_preguntar and args.indices is None:
        confirm = input("  ¿Continuar? (s/n): ").strip().lower()
        if confirm != 's':
            print("  Cancelado.")
            return

    # Descargar
    print("\n  🚀 INICIANDO DESCARGA...")
    for i, img in enumerate(seleccion, 1):
        print(f"\n  [{i}/{len(seleccion)}]")
        resultado = descargar_imagen(img, token)
        if resultado is None:
            print("  Renovando token...")
            token = obtener_token(usuario, password)
            if not token:
                print("  No se pudo renovar token. Abortando.")
                break
            resultado = descargar_imagen(img, token)

    print("\n" + "=" * 70)
    print("  PROCESO COMPLETADO")
    print("=" * 70)

if __name__ == "__main__":
    main()