#!/usr/bin/env python3
"""
00_identificar_tiles.py
Identifica los tiles Sentinel-2 que cubren un polígono.
Usa los vértices del polígono para encontrar tiles candidatos,
disuelve geometrías duplicadas y calcula áreas de intersección.
Opcionalmente guarda la lista de tiles en un archivo.
"""

import sys
import argparse
from pathlib import Path

import geopandas as gpd
from shapely import wkt
import pandas as pd
import numpy as np

# ========== CONFIGURACIÓN ==========
AREA_WKT = Path("area.wkt")
MGRS_SHP = Path("../datos/raw/Sentinel-2-Shapefile-Index-master/sentinel_2_index_shapefile.shp")

def cargar_poligono(archivo):
    """Carga polígono desde archivo WKT."""
    with open(archivo, 'r') as f:
        wkt_str = f.read().strip().split('\n')[0]
    geom = wkt.loads(wkt_str)
    return gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")

def area_km2_utm(geom):
    """Calcula área en km² de una geometría (EPSG:4326) proyectándola a su UTM local."""
    lon = geom.centroid.x
    lat = geom.centroid.y
    zona = int(np.floor((lon + 180) / 6)) + 1
    epsg = f"EPSG:326{zona:02d}" if lat >= 0 else f"EPSG:327{zona:02d}"
    proj = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(epsg)
    return proj.area.iloc[0] / 1e6

def main():
    parser = argparse.ArgumentParser(
        description="Identifica tiles Sentinel-2 que cubren un polígono."
    )
    parser.add_argument("--area", help="Archivo WKT con el polígono (por defecto area.wkt)")
    parser.add_argument("--tiles-shp", help="Shapefile de la grilla MGRS de Sentinel-2")
    parser.add_argument("--guardar-csv", help="Guardar tabla de resultados en CSV")
    parser.add_argument("--guardar-tiles", help="Guardar lista de tiles (uno por línea) en archivo")
    args = parser.parse_args()

    print("=" * 70)
    print("  IDENTIFICACIÓN DE TILES SENTINEL-2")
    print("=" * 70)

    # 1. Cargar polígono
    archivo_poly = args.area if args.area else AREA_WKT
    print(f"\n[1/5] Cargando polígono desde {archivo_poly}...")
    aoi = cargar_poligono(archivo_poly)
    print("  OK")

    # 2. Cargar teselas
    tiles_shp = args.tiles_shp if args.tiles_shp else MGRS_SHP
    print(f"\n[2/5] Cargando teselas desde {tiles_shp}...")
    if not Path(tiles_shp).exists():
        print(f"  ERROR: No se encuentra {tiles_shp}")
        sys.exit(1)
    tiles = gpd.read_file(tiles_shp)
    # Asegurar CRS WGS84
    if tiles.crs != "EPSG:4326":
        tiles = tiles.to_crs("EPSG:4326")
    print(f"  Se cargaron {len(tiles)} registros.")

    # 3. Extraer vértices del polígono
    print("\n[3/5] Extrayendo vértices del polígono...")
    polygon = aoi.geometry.iloc[0]
    if polygon.geom_type == 'Polygon':
        coords = list(polygon.exterior.coords)
    elif polygon.geom_type == 'MultiPolygon':
        coords = []
        for poly in polygon.geoms:
            coords.extend(poly.exterior.coords)
    else:
        print("  Tipo de geometría no soportado.")
        sys.exit(1)

    points = gpd.GeoDataFrame(geometry=gpd.points_from_xy([c[0] for c in coords], [c[1] for c in coords]), crs="EPSG:4326")
    print(f"  Se extrajeron {len(points)} vértices.")

    # 4. Encontrar teselas que contienen algún vértice
    print("\n[4/5] Identificando teselas que contienen algún vértice...")
    candidate = gpd.sjoin(points, tiles, how="inner", predicate="within")
    if candidate.empty:
        print("  No se encontraron teselas que contengan los vértices. Buscando por intersección...")
        candidate = gpd.sjoin(tiles, aoi, how="inner", predicate="intersects")
        if candidate.empty:
            print("  No se encontró ninguna tesela.")
            return
        print(f"  Se encontraron {candidate['index_right'].nunique()} teselas por intersección.")
    else:
        print(f"  Se encontraron {candidate['index_right'].nunique()} teselas candidatas.")

    # Obtener IDs únicos de teselas
    # Detectar columna de ID
    id_campo = None
    for col in ['tile_id', 'Name', 'tile', 'id', 'TILE_ID', 'NAME']:
        if col in candidate.columns:
            id_campo = col
            break
    if id_campo is None:
        print("  No se pudo identificar el campo de ID. Usando índice original.")
        candidate['tile_id'] = candidate.index_right
        id_campo = 'tile_id'

    tiles_ids = candidate[id_campo].unique()
    print(f"  Teselas candidatas: {', '.join(map(str, tiles_ids))}")

    # 5. Disolver y calcular áreas de intersección
    print("\n[5/5] Calculando áreas de intersección...")
    tiles_candidates = tiles[tiles[id_campo].isin(tiles_ids)].copy()
    tiles_dissolved = tiles_candidates.dissolve(by=id_campo)

    area_total_poligono = area_km2_utm(polygon)
    print(f"  Área total del polígono: {area_total_poligono:.2f} km²")

    resultados = []
    for tile_id, geom_tile in tiles_dissolved.geometry.items():
        clip = polygon.intersection(geom_tile)
        if clip.is_empty:
            continue
        area_int = area_km2_utm(clip)
        centro = clip.centroid
        lon, lat = centro.x, centro.y
        pct_poly = (area_int / area_total_poligono) * 100
        pct_tile = (area_int / 10000) * 100
        resultados.append({
            "TileID": tile_id,
            "Centro_lon": lon,
            "Centro_lat": lat,
            "Area_intersect_km2": area_int,
            "%_del_poligono": pct_poly,
            "%_del_tile": pct_tile
        })

    if not resultados:
        print("  No se encontraron áreas de intersección.")
        return

    tabla = pd.DataFrame(resultados)
    tabla = tabla.sort_values("Area_intersect_km2", ascending=False)

    # Verificar suma
    suma = tabla["Area_intersect_km2"].sum()
    if abs(suma - area_total_poligono) > 1e-3:
        print(f"\n  ADVERTENCIA: La suma de áreas intersectadas ({suma:.2f} km²) difiere del área total ({area_total_poligono:.2f} km²).")
        print("  Esto puede deberse a solapamientos en la grilla o errores numéricos.")

    print("\n  RESULTADOS:")
    print(tabla.to_string(index=False))

    if args.guardar_csv:
        tabla.to_csv(args.guardar_csv, index=False)
        print(f"\n  Tabla guardada en {args.guardar_csv}")

    if args.guardar_tiles:
        try:
            with open(args.guardar_tiles, 'w') as f:
                for tid in tiles_ids:
                    f.write(f"{tid}\n")
            print(f"\n  Lista de tiles guardada en {args.guardar_tiles}")
        except Exception as e:
            print(f"  Error guardando lista de tiles: {e}")

    print("\n" + "=" * 70)
    print("  LISTO")
    print("=" * 70)

if __name__ == "__main__":
    main()