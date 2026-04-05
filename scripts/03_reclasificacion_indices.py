#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║   RECLASIFICACIÓN DE ÍNDICES ESPECTRALES — Sentinel-2 v3.1     ║
╠══════════════════════════════════════════════════════════════════╣
║  Nuevo índice: MNDWI (Modified NDWI) usando SWIR1                ║
║  Rangos ajustados para agua, humedad y suelo seco               ║
║  Genera colormap y archivo .qml para QGIS                        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
import geopandas as gpd
import pandas as pd
from shapely.validation import make_valid
import warnings
warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN GENERAL
# ══════════════════════════════════════════════════════════════════

CONFIG = {
    'carpeta_indices'  : r'F:\geodatos-ecuador\datos\processed\Podocarprocessed\indices',
    'shapefile'        : r'F:\geodatos-ecuador\datos\aoi\Podocarpus\podocarpus_wgs84.shp',
    'carpeta_salida'   : r'F:\geodatos-ecuador\datos\processed\Podocarprocessed\clasificacion',
    'nodata'           : -9999,
    'indices'          : ['NDVI', 'NDWI', 'MNDWI', 'SAVI', 'EVI', 'NBR'],
    'resolucion_m'     : 10,
}

# ══════════════════════════════════════════════════════════════════
#  TABLA DE RECLASIFICACIÓN (rangos ajustados)
# ══════════════════════════════════════════════════════════════════

TABLA_CLASES = {

    'NDVI': [
        (1, None, 0.0,   'Agua / Nieve / Nubes',
         'Valores negativos: agua, nieve o nubes densas.'),
        (2, 0.0, 0.2,    'Suelo desnudo / Roca / Arena',
         'Suelo expuesto, rocas o áreas urbanas.'),
        (3, 0.2, 0.5,    'Vegetación escasa / Pastizal',
         'Vegetación de baja densidad, pastizales, cultivos.'),
        (4, 0.5, None,   'Vegetación densa / Bosque',
         'Bosque denso, vegetación saludable.'),
    ],

    'NDWI': [
        (1, None, 0.0,   'Suelo seco / Vegetación estresada',
         'Superficies secas, suelo desnudo.'),
        (2, 0.0, 0.05,   'Zonas urbanas / Infraestructura',
         'Edificaciones, carreteras.'),
        (3, 0.05, 0.2,   'Vegetación hidratada / Humedad moderada',
         'Vegetación con buen estado hídrico.'),
        (4, 0.2, None,   'Agua abierta / Inundación',
         'Cuerpos de agua claros, humedales.'),
    ],

    'MNDWI': [
        (1, None, 0.0,   'Suelo seco / Urbano',
         'Superficies secas, áreas urbanas, suelo desnudo.'),
        (2, 0.0, 0.1,    'Humedad baja / Vegetación estresada',
         'Suelo con algo de humedad o vegetación con estrés.'),
        (3, 0.1, 0.2,    'Humedad moderada / Vegetación hidratada',
         'Vegetación con buen contenido hídrico.'),
        (4, 0.2, None,   'Agua abierta / Inundación',
         'Cuerpos de agua claros, humedales, inundaciones.'),
    ],

    'SAVI': [
        (1, None, 0.0,   'Agua / Sombras / Nubes',
         'Agua, sombras de nubes.'),
        (2, 0.0, 0.3,    'Suelo desnudo / Vegetación muy escasa',
         'Suelo expuesto, cobertura vegetal <10%.'),
        (3, 0.3, 0.55,   'Vegetación moderada / Cultivos',
         'Vegetación en crecimiento, cultivos.'),
        (4, 0.55, None,  'Vegetación densa / Bosque',
         'Bosque cerrado, vegetación vigorosa.'),
    ],

    'EVI': [
        (1, None, 0.0,   'Nubes / Nieve / Agua turbia',
         'Anomalías atmosféricas.'),
        (2, 0.0, 0.2,    'Urbano / Suelo sin cobertura',
         'Áreas urbanas, suelo desnudo.'),
        (3, 0.2, 0.5,    'Vegetación moderada',
         'Bosques secundarios, cultivos.'),
        (4, 0.5, None,   'Selva / Alta biomasa',
         'Bosques tropicales densos.'),
    ],

    'NBR': [
        (1, None, 0.0,   'Área quemada / Agua',
         'Incendio reciente o agua.'),
        (2, 0.0, 0.1,    'Suelo desnudo / Vegetación estresada',
         'Suelo expuesto, zonas degradadas.'),
        (3, 0.1, 0.4,    'Vegetación en recuperación / Pastizal',
         'Vegetación post-incendio o pastizales.'),
        (4, 0.4, None,   'Vegetación sana y vigorosa',
         'Bosque sano, alta cobertura.'),
    ],
}

# ══════════════════════════════════════════════════════════════════
#  COLORMAP Y ESTILO QGIS (paleta de colores)
# ══════════════════════════════════════════════════════════════════

# Colores en formato RGBA (0-255)
COLORMAP = {
    0: (44, 44, 42, 0),      # NoData transparente
    1: (55, 138, 221, 255),  # Azul (agua)
    2: (239, 159, 39, 255),  # Ámbar (suelo)
    3: (151, 196, 89, 255),  # Verde claro (vegetación escasa/moderada)
    4: (29, 158, 117, 255),  # Verde oscuro (vegetación densa)
}

def generar_estilo_qml(ruta_qml, nombre_indice):
    """Genera un archivo .qml (estilo de QGIS) para el raster de clases."""
    # Ajustar etiquetas según el índice
    if nombre_indice == 'MNDWI':
        etiquetas = {
            1: 'Suelo seco / Urbano',
            2: 'Humedad baja',
            3: 'Humedad moderada',
            4: 'Agua abierta'
        }
    elif nombre_indice == 'NDWI':
        etiquetas = {
            1: 'Suelo seco',
            2: 'Zonas urbanas',
            3: 'Vegetación hidratada',
            4: 'Agua abierta'
        }
    elif nombre_indice == 'NDVI':
        etiquetas = {
            1: 'Agua / Nieve',
            2: 'Suelo desnudo',
            3: 'Vegetación escasa',
            4: 'Vegetación densa'
        }
    elif nombre_indice == 'SAVI':
        etiquetas = {
            1: 'Agua / Sombras',
            2: 'Suelo desnudo',
            3: 'Vegetación moderada',
            4: 'Vegetación densa'
        }
    elif nombre_indice == 'EVI':
        etiquetas = {
            1: 'Nubes / Nieve',
            2: 'Urbano / Suelo',
            3: 'Vegetación moderada',
            4: 'Selva / Alta biomasa'
        }
    elif nombre_indice == 'NBR':
        etiquetas = {
            1: 'Área quemada / Agua',
            2: 'Suelo desnudo',
            3: 'Vegetación recuperación',
            4: 'Vegetación sana'
        }
    else:
        etiquetas = {1: 'Clase 1', 2: 'Clase 2', 3: 'Clase 3', 4: 'Clase 4'}

    qml_content = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" style="categories">
  <rastershader>
    <rasterrenderer type="paletted" band="1" opacity="1" alpha="-1">
      <colorPalette>
        <paletteEntry value="1" color="#378ADD" label="{etiquetas[1]}" alpha="255"/>
        <paletteEntry value="2" color="#EF9F27" label="{etiquetas[2]}" alpha="255"/>
        <paletteEntry value="3" color="#97C459" label="{etiquetas[3]}" alpha="255"/>
        <paletteEntry value="4" color="#1D9E75" label="{etiquetas[4]}" alpha="255"/>
      </colorPalette>
    </rasterrenderer>
  </rastershader>
  <legend type="paletted"/>
</qgis>"""
    with open(ruta_qml, 'w', encoding='utf-8') as f:
        f.write(qml_content)

# ══════════════════════════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════════════════════════

def log(msg, nivel=0):
    print('  ' * nivel + msg)

def reparar_geometria(geom):
    if geom.is_valid:
        return geom
    try:
        return make_valid(geom)
    except:
        return geom.buffer(0)

def recortar_con_shapefile(ruta_tif, shapefile_gdf, nodata):
    with rasterio.open(ruta_tif) as src:
        crs_raster = src.crs
        try:
            epsg = crs_raster.to_epsg() if crs_raster else None
            if epsg:
                shp = shapefile_gdf.to_crs(epsg=epsg)
            else:
                shp = shapefile_gdf.to_crs(crs_raster.to_wkt())
        except:
            shp = shapefile_gdf
        shp['geometry'] = shp['geometry'].apply(reparar_geometria)
        shp = shp[shp.is_valid]
        if shp.empty:
            raise ValueError("Shapefile sin geometrías válidas")
        geometrias = [g.__geo_interface__ for g in shp.geometry]
        datos, transform = rio_mask(src, geometrias, crop=True, nodata=nodata)
        perfil = src.profile.copy()
        perfil.update({
            'height': datos.shape[1],
            'width': datos.shape[2],
            'transform': transform,
            'nodata': nodata,
        })
    return datos[0].astype('float32'), perfil

def reclasificar_seguro(datos, clases, nodata):
    mascara_valida = ~(np.isnan(datos) | (datos == nodata) | (np.abs(datos - nodata) < 1e-6))
    resultado = np.zeros(datos.shape, dtype=np.uint8)
    for valor_clase, lim_inf, lim_sup, _, _ in clases:
        if lim_inf is None and lim_sup is not None:
            cond = (datos < lim_sup) & mascara_valida
        elif lim_inf is not None and lim_sup is None:
            cond = (datos >= lim_inf) & mascara_valida
        else:
            cond = (datos >= lim_inf) & (datos < lim_sup) & mascara_valida
        resultado[cond] = valor_clase
    restantes = mascara_valida & (resultado == 0)
    if restantes.any():
        log(f'  Advertencia: {restantes.sum()} píxeles válidos no clasificados (asignados a NoData).', 2)
        resultado[restantes] = 0
    return resultado

def guardar_raster_con_colormap(ruta, datos_clases, perfil, colormap):
    p = perfil.copy()
    p.update({
        'count': 1,
        'dtype': 'uint8',
        'nodata': 0,
        'compress': None,   # Sin compresión para máxima compatibilidad
        'driver': 'GTiff',
    })
    with rasterio.open(ruta, 'w', **p) as dst:
        dst.write(datos_clases, 1)
        dst.write_colormap(1, colormap)

def calcular_area_por_clase(datos_clases, clases, resolucion_m, nodata_mask):
    area_pixel_ha = (resolucion_m * resolucion_m) / 10000
    total_pixeles = int((~nodata_mask).sum())
    total_ha = total_pixeles * area_pixel_ha
    filas = []
    n_nodata = int(nodata_mask.sum())
    filas.append({
        'Clase': 0,
        'Etiqueta': 'Sin datos (NoData)',
        'Descripción': 'Píxeles fuera del área o nubes persistentes',
        'Píxeles': n_nodata,
        'Área (ha)': round(n_nodata * area_pixel_ha, 2),
        'Área (km²)': round(n_nodata * area_pixel_ha / 100, 2),
        'Porcentaje (%)': round(100 * n_nodata / (total_pixeles + n_nodata), 2) if (total_pixeles + n_nodata) > 0 else 0,
    })
    for valor_clase, _, _, etiqueta, descripcion in clases:
        n = int((datos_clases == valor_clase).sum())
        area_ha = n * area_pixel_ha
        pct = round(100 * n / total_pixeles, 2) if total_pixeles > 0 else 0
        filas.append({
            'Clase': valor_clase,
            'Etiqueta': etiqueta,
            'Descripción': descripcion,
            'Píxeles': n,
            'Área (ha)': round(area_ha, 2),
            'Área (km²)': round(area_ha / 100, 2),
            'Porcentaje (%)': pct,
        })
    filas.append({
        'Clase': 'TOTAL',
        'Etiqueta': 'Área válida total',
        'Descripción': 'Suma de todas las clases dentro del polígono',
        'Píxeles': total_pixeles,
        'Área (ha)': round(total_ha, 2),
        'Área (km²)': round(total_ha / 100, 2),
        'Porcentaje (%)': 100.0,
    })
    return pd.DataFrame(filas)

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    print('╔══════════════════════════════════════════════════╗')
    print('║   RECLASIFICACIÓN DE ÍNDICES ESPECTRALES v3.1   ║')
    print('╚══════════════════════════════════════════════════╝\n')

    os.makedirs(CONFIG['carpeta_salida'], exist_ok=True)

    # Cargar shapefile
    log('Cargando shapefile...')
    gdf = gpd.read_file(CONFIG['shapefile'])
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:4326')
    gdf['geometry'] = gdf['geometry'].apply(reparar_geometria)
    gdf = gdf[gdf.is_valid]
    log(f'  CRS: {gdf.crs} | Geometrías válidas: {len(gdf)}')

    nodata = CONFIG['nodata']
    resolucion_m = CONFIG['resolucion_m']
    reportes = {}

    for idx in CONFIG['indices']:
        ruta_idx = os.path.join(CONFIG['carpeta_indices'], f'{idx}.tif')
        if not os.path.exists(ruta_idx):
            log(f'\n⚠ No encontrado: {ruta_idx} — omitiendo')
            continue

        log(f'\n═══ {idx} ═══')
        try:
            # Recortar
            log('  [1/4] Recortando con shapefile...', 1)
            datos, perfil = recortar_con_shapefile(ruta_idx, gdf, nodata)
            log(f'    Shape: {datos.shape}', 2)

            validos = datos[datos != nodata]
            if len(validos) == 0:
                log('  ✗ Sin datos válidos — omitiendo', 1)
                continue
            log(f'    Valores originales: min={validos.min():.3f} | max={validos.max():.3f} | media={validos.mean():.3f}', 2)

            # Reclasificar
            log('  [2/4] Reclasificando según tabla...', 1)
            clases = TABLA_CLASES[idx]
            datos_clases = reclasificar_seguro(datos, clases, nodata)
            mascara_nodata = datos == nodata

            # Guardar raster con colormap
            ruta_clases = os.path.join(CONFIG['carpeta_salida'], f'{idx}_clases.tif')
            guardar_raster_con_colormap(ruta_clases, datos_clases, perfil, COLORMAP)
            log(f'    Guardado → {ruta_clases}', 2)

            # Generar archivo .qml para QGIS
            ruta_qml = os.path.join(CONFIG['carpeta_salida'], f'{idx}_clases.qml')
            generar_estilo_qml(ruta_qml, idx)
            log(f'    Estilo QML → {ruta_qml}', 2)

            # Calcular áreas
            log('  [3/4] Calculando áreas por clase...', 1)
            df = calcular_area_por_clase(datos_clases, clases, resolucion_m, mascara_nodata)
            reportes[idx] = df

            # Mostrar resumen
            log(f'\n  {"Clase":<5} {"Etiqueta":<28} {"Píxeles":>10} {"Área (ha)":>12} {"(%)":>8}', 1)
            log('  ' + '-' * 75, 1)
            for _, row in df.iterrows():
                if row['Clase'] == 0:
                    continue
                log(f'  {row["Clase"]:<5} {row["Etiqueta"]:<28} {row["Píxeles"]:>10,} {row["Área (ha)"]:>12,.2f} {row["Porcentaje (%)"]:>7.1f}%', 1)
            total_row = df[df['Clase'] == 'TOTAL'].iloc[0]
            log('  ' + '-' * 75, 1)
            log(f'  {"TOTAL":<5} {"Área válida total":<28} {total_row["Píxeles"]:>10,} {total_row["Área (ha)"]:>12,.2f} {"100.0":>7}%', 1)

            # Guardar CSV
            ruta_csv = os.path.join(CONFIG['carpeta_salida'], f'{idx}_reporte.csv')
            df.to_csv(ruta_csv, index=False, encoding='utf-8-sig')
            log(f'\n  ✅ Reporte → {ruta_csv}', 1)

        except Exception as e:
            log(f'  ❌ Error procesando {idx}: {e}', 1)
            continue

    # Reporte global
    if reportes:
        log('\n═══ Generando reporte global ═══')
        filas_global = []
        for idx, df in reportes.items():
            for _, row in df.iterrows():
                filas_global.append({
                    'Índice': idx,
                    'Clase': row['Clase'],
                    'Etiqueta': row['Etiqueta'],
                    'Descripción': row['Descripción'],
                    'Píxeles': row['Píxeles'],
                    'Área (ha)': row['Área (ha)'],
                    'Área (km²)': row['Área (km²)'],
                    'Porcentaje (%)': row['Porcentaje (%)'],
                })
        df_global = pd.DataFrame(filas_global)
        ruta_global = os.path.join(CONFIG['carpeta_salida'], 'reporte_indices_global.csv')
        df_global.to_csv(ruta_global, index=False, encoding='utf-8-sig')
        log(f'  ✅ Reporte global → {ruta_global}')

    print('\n╔══════════════════════════════════════════════════╗')
    print('║   RECLASIFICACIÓN COMPLETADA                     ║')
    print('╚══════════════════════════════════════════════════╝')
    print(f'\nArchivos generados en: {CONFIG["carpeta_salida"]}')
    print('  • *_clases.tif → rasters de clases (con colormap)')
    print('  • *_clases.qml → estilos de QGIS')
    print('  • *_reporte.csv → estadísticas por índice')
    print('  • reporte_indices_global.csv → consolidado')

if __name__ == '__main__':
    main()