#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║   PIPELINE SENTINEL-2 — Flujo completo v4.2                     ║
╠══════════════════════════════════════════════════════════════════╣
║  Nuevo índice: MNDWI (Modified NDWI) usando SWIR1                ║
║  Calcula: (B03 - B11) / (B03 + B11)  → más robusto para agua    ║
║  Mantiene NDVI, NDWI, SAVI, EVI, NBR                            ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys

# ── Fix conflicto PROJ PostgreSQL vs rasterio ─────────────────────
os.environ.pop('PROJ_LIB',  None)
os.environ.pop('PROJ_DATA', None)
import pathlib
for p in sys.path:
    proj_candidate = pathlib.Path(p) / 'rasterio' / 'proj_data'
    if proj_candidate.exists():
        os.environ['PROJ_DATA'] = str(proj_candidate)
        os.environ['PROJ_LIB']  = str(proj_candidate)
        break

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.mask import mask as rio_mask
from rasterio.warp import reproject
from rasterio.crs import CRS
import geopandas as gpd
from pathlib import Path
import glob
import xml.etree.ElementTree as ET
import warnings
warnings.filterwarnings('ignore')

# OpenCV opcional
try:
    import cv2
    OPENCV_DISPONIBLE = True
except ImportError:
    OPENCV_DISPONIBLE = False

# ══════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN (editar rutas según tu sistema)
# ══════════════════════════════════════════════════════════════════

CONFIG = {
    'carpeta_safe'     : r'F:\geodatos-ecuador\datos\raw\Podocarpus',
    'shapefile'        : r'F:\geodatos-ecuador\datos\aoi\Podocarpus\podocarpus_wgs84.shp',
    'carpeta_salida'   : r'F:\geodatos-ecuador\datos\processed\Podocarprocessed',
    'nombre_salida'    : 'mosaico_sentinel2_multibanda.tif',
    'prioridad_fechas' : ['20240704', '20240912', '20241002', '20241111'],

    'bandas': [
        ('B2',  1, 'Azul'),
        ('B3',  2, 'Verde'),
        ('B4',  3, 'Rojo'),
        ('B8',  4, 'NIR'),
        ('B11', 5, 'SWIR1'),
        ('B12', 6, 'SWIR2'),
    ],

    'resolucion_m'    : 10,
    'scl_clases_nube' : [0,2,3,8,9,10],
    'nodata'          : -9999,

    'modo_mosaico': 2,               # 1=simple, 2=normalización, 3=blending
    'fecha_referencia_norm': 'auto',
    'blending_px': 2,
    'relleno_huecos': 'opencv',      # 'opencv' o 'vecino'
    'calcular_indices': True,
    'indices': ['NDVI', 'NDWI', 'MNDWI', 'SAVI', 'EVI', 'NBR'],
}

# ══════════════════════════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════════════════════════

def log(msg, nivel=0):
    print('  ' * nivel + msg)

def encontrar_banda_safe(carpeta_safe, banda):
    nombre_con_cero = {
        'B2': 'B02', 'B3': 'B03', 'B4': 'B04',
        'B5': 'B05', 'B6': 'B06', 'B7': 'B07',
        'B8': 'B08', 'B9': 'B09',
    }
    res_nativa = {
        'B2': '10m', 'B3': '10m', 'B4': '10m', 'B8': '10m',
        'B11': '20m', 'B12': '20m', 'SCL': '20m',
    }
    alias = nombre_con_cero.get(banda, banda)
    res   = res_nativa.get(banda, '*m')
    patrones = (
        ['**/IMG_DATA/R20m/*_SCL_20m.jp2',
         '**/IMG_DATA/R60m/*_SCL_60m.jp2',
         '**/IMG_DATA/**/*SCL*.jp2']
        if banda == 'SCL' else
        [f'**/IMG_DATA/R{res}/*_{alias}_{res}.jp2',
         f'**/IMG_DATA/R{res}/*_{banda}_{res}.jp2',
         f'**/IMG_DATA/**/*_{alias}_*.jp2',
         f'**/IMG_DATA/**/*_{banda}_*.jp2']
    )
    for patron in patrones:
        archivos = list(Path(carpeta_safe).glob(patron))
        if archivos:
            return str(archivos[0])
    return None

def leer_crs_xml(carpeta_safe):
    ruta_xml = os.path.join(carpeta_safe, 'MTD_MSIL2A.xml')
    if not os.path.exists(ruta_xml):
        return None
    try:
        for elem in ET.parse(ruta_xml).getroot().iter():
            texto = (elem.text or '').strip()
            if 'EPSG:' in texto:
                return CRS.from_epsg(int(texto.split('EPSG:')[-1]))
    except Exception:
        pass
    return None

def crs_utm17s():
    return CRS.from_wkt(
        'PROJCS["WGS 84 / UTM zone 17S",'
        'GEOGCS["WGS 84",DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
        'PROJECTION["Transverse_Mercator"],'
        'PARAMETER["latitude_of_origin",0],'
        'PARAMETER["central_meridian",-81],'
        'PARAMETER["scale_factor",0.9996],'
        'PARAMETER["false_easting",500000],'
        'PARAMETER["false_northing",10000000],'
        'UNIT["metre",1]]'
    )

def resamplear(ruta_src, resolucion_m, metodo=Resampling.cubic):
    with rasterio.open(ruta_src) as src:
        escala  = src.res[0] / resolucion_m
        nuevo_w = int(src.width  * escala)
        nuevo_h = int(src.height * escala)
        nuevo_t = rasterio.transform.from_bounds(
            *src.bounds, width=nuevo_w, height=nuevo_h
        )
        datos = src.read(
            out_shape=(src.count, nuevo_h, nuevo_w),
            resampling=metodo,
        ).astype('float32')
        perfil = src.profile.copy()
        perfil.update({
            'width': nuevo_w, 'height': nuevo_h, 'transform': nuevo_t,
            'driver': 'GTiff', 'dtype': 'float32',
            'nodata': CONFIG['nodata'], 'compress': 'lzw',
        })
    return datos, perfil

def leer_banda_tif(ruta, num_banda):
    with rasterio.open(ruta) as src:
        datos  = src.read(num_banda).astype('float32')
        perfil = src.profile.copy()
        perfil.update({'count': 1, 'dtype': 'float32', 'nodata': CONFIG['nodata']})
        if src.nodata is not None and src.nodata != CONFIG['nodata']:
            datos[datos == src.nodata] = CONFIG['nodata']
    return datos, perfil

def alinear_grids(datos_src, perfil_src, perfil_dst):
    if (datos_src.shape == (perfil_dst['height'], perfil_dst['width']) and
            perfil_src['transform'] == perfil_dst['transform']):
        return datos_src
    dest = np.full(
        (perfil_dst['height'], perfil_dst['width']),
        CONFIG['nodata'], dtype='float32'
    )
    reproject(
        source=datos_src, destination=dest,
        src_transform=perfil_src['transform'], src_crs=perfil_src['crs'],
        dst_transform=perfil_dst['transform'], dst_crs=perfil_dst['crs'],
        resampling=Resampling.cubic_spline,
        src_nodata=CONFIG['nodata'], dst_nodata=CONFIG['nodata'],
    )
    return dest

def rellenar_huecos(banda, nodata):
    mascara_hueco = (banda == nodata)
    if not mascara_hueco.any():
        return banda
    resultado = banda.copy()
    if CONFIG['relleno_huecos'] == 'opencv' and OPENCV_DISPONIBLE:
        validos = banda[~mascara_hueco]
        vmin, vmax = validos.min(), validos.max()
        if vmax == vmin:
            return resultado
        banda_norm = np.clip((banda - vmin) / (vmax - vmin) * 255, 0, 255).astype(np.uint8)
        banda_norm[mascara_hueco] = 0
        mascara_uint8 = mascara_hueco.astype(np.uint8) * 255
        relleno_norm = cv2.inpaint(banda_norm, mascara_uint8, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        relleno_orig = relleno_norm.astype('float32') / 255.0 * (vmax - vmin) + vmin
        resultado[mascara_hueco] = relleno_orig[mascara_hueco]
    else:
        from scipy.ndimage import distance_transform_edt
        _, indices = distance_transform_edt(mascara_hueco, return_indices=True)
        resultado = banda[indices[0], indices[1]]
    return resultado

# ══════════════════════════════════════════════════════════════════
#  MODOS DE MOSAICO
# ══════════════════════════════════════════════════════════════════

def normalizar_banda(datos, nodata):
    validos = datos[datos != nodata]
    if len(validos) == 0:
        return 0.0, 1.0
    return float(validos.mean()), float(validos.std() + 1e-10)

def aplicar_normalizacion(datos, mu_src, sigma_src, mu_ref, sigma_ref, nodata):
    resultado = datos.copy()
    mascara   = datos != nodata
    resultado[mascara] = (
        (datos[mascara] - mu_src) / sigma_src * sigma_ref + mu_ref
    )
    return resultado

def mosaico_simple(rutas, num_banda, perfil_ref, nodata):
    mosaico, p = leer_banda_tif(rutas[0], num_banda)
    for ruta in rutas[1:]:
        if (mosaico == nodata).sum() == 0:
            break
        datos, ps = leer_banda_tif(ruta, num_banda)
        datos = alinear_grids(datos, ps, perfil_ref)
        mosaico = np.where(mosaico == nodata, datos, mosaico)
    return mosaico

def mosaico_normalizado(rutas, num_banda, perfil_ref, nodata):
    base, p = leer_banda_tif(rutas[0], num_banda)
    mu_ref, sigma_ref = normalizar_banda(base, nodata)
    log(f'      Referencia μ={mu_ref:.1f} σ={sigma_ref:.1f}', 3)
    mosaico = base.copy()
    for ruta in rutas[1:]:
        if (mosaico == nodata).sum() == 0:
            break
        datos, ps = leer_banda_tif(ruta, num_banda)
        datos = alinear_grids(datos, ps, perfil_ref)
        mu_src, sigma_src = normalizar_banda(datos, nodata)
        log(f'      {os.path.basename(ruta)[:20]} μ={mu_src:.1f} σ={sigma_src:.1f} → normalizado', 3)
        datos_norm = aplicar_normalizacion(datos, mu_src, sigma_src, mu_ref, sigma_ref, nodata)
        mosaico = np.where(mosaico == nodata, datos_norm, mosaico)
    return mosaico

def mosaico_blending(rutas, num_banda, perfil_ref, nodata, blending_px=2):
    from scipy.ndimage import distance_transform_edt, uniform_filter, binary_dilation
    base, p = leer_banda_tif(rutas[0], num_banda)
    mosaico = base.copy()
    for ruta in rutas[1:]:
        if (mosaico == nodata).sum() == 0:
            break
        datos, ps = leer_banda_tif(ruta, num_banda)
        datos = alinear_grids(datos, ps, perfil_ref)
        mascara_hueco = mosaico == nodata
        if not mascara_hueco.any():
            break
        dist = distance_transform_edt(~mascara_hueco).astype('float32')
        dist = np.clip(dist / blending_px, 0, 1)
        zona_blend = (dist < 1) & (~mascara_hueco) & (datos != nodata)
        mosaico = np.where(mascara_hueco, datos, mosaico)
        if zona_blend.any():
            blend = dist[zona_blend]
            mosaico[zona_blend] = (
                mosaico[zona_blend] * blend +
                datos[zona_blend]   * (1 - blend)
            )
    if blending_px > 0:
        mascara_valida = mosaico != nodata
        suavizado = uniform_filter(
            np.where(mascara_valida, mosaico, 0).astype('float32'),
            size=blending_px * 2 + 1,
        )
        borde = (~mascara_valida.astype(bool))
        zona_borde = binary_dilation(borde, iterations=blending_px) & mascara_valida
        mosaico[zona_borde] = suavizado[zona_borde]
    return mosaico

# ══════════════════════════════════════════════════════════════════
#  ÍNDICES ESPECTRALES (INCLUYE MNDWI)
# ══════════════════════════════════════════════════════════════════

def calcular_indice(nombre, bandas_dict, nodata):
    """
    Calcula un índice espectral.
    bandas_dict: {'B2': array, ...} con valores en DN (0-10000)
    """
    eps = 1e-10
    nodata_mask = None

    def get(banda):
        nonlocal nodata_mask
        arr = bandas_dict[banda].astype('float32')
        msk = (arr == nodata)
        if nodata_mask is None:
            nodata_mask = msk
        else:
            nodata_mask = nodata_mask | msk
        # Convertir a reflectancia (0-1) dividiendo por 10000
        arr = np.where(msk, np.nan, arr / 10000.0)
        return arr

    if nombre == 'NDVI':
        nir, red = get('B8'), get('B4')
        indice = (nir - red) / (nir + red + eps)
    elif nombre == 'NDWI':
        green, nir = get('B3'), get('B8')
        indice = (green - nir) / (green + nir + eps)
    elif nombre == 'MNDWI':
        green, swir1 = get('B3'), get('B11')
        indice = (green - swir1) / (green + swir1 + eps)
    elif nombre == 'SAVI':
        nir, red = get('B8'), get('B4')
        L = 0.5
        indice = ((nir - red) / (nir + red + L + eps)) * (1 + L)
    elif nombre == 'EVI':
        nir, red, blue = get('B8'), get('B4'), get('B2')
        indice = 2.5 * (nir - red) / (nir + 6*red - 7.5*blue + 1 + eps)
        indice = np.clip(indice, -1, 1)
    elif nombre == 'NBR':
        nir, swir2 = get('B8'), get('B12')
        indice = (nir - swir2) / (nir + swir2 + eps)
    else:
        return None

    indice = np.where(np.isnan(indice) | nodata_mask, nodata, indice)
    return indice.astype('float32')

def guardar_indice(nombre, datos, perfil, carpeta_salida):
    """Guarda el índice en float32 sin escalar (rango -1 a 1)."""
    ruta = os.path.join(carpeta_salida, 'indices', f'{nombre}.tif')
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    p = perfil.copy()
    p.update({
        'count': 1,
        'dtype': 'float32',
        'nodata': CONFIG['nodata'],
        'compress': 'lzw',
        'driver': 'GTiff',
    })
    with rasterio.open(ruta, 'w', **p) as dst:
        dst.write(datos, 1)
        dst.update_tags(1, name=nombre)
    log(f'  ✓ {nombre} → {ruta}', 2)

# ══════════════════════════════════════════════════════════════════
#  PROCESAR FECHA
# ══════════════════════════════════════════════════════════════════

def procesar_fecha(carpeta_safe, fecha, shapefile_gdf, carpeta_salida):
    ruta_salida = os.path.join(
        carpeta_salida, 'por_fecha', f'sentinel2_{fecha}_masked.tif'
    )
    if os.path.exists(ruta_salida):
        log(f'  Ya existe → omitiendo: {os.path.basename(ruta_salida)}', 1)
        return ruta_salida

    log(f'\n══ Fecha: {fecha} ══')

    log('  [1/4] Buscando bandas...', 1)
    bandas_rutas = {}
    for nombre, _, _ in CONFIG['bandas']:
        ruta = encontrar_banda_safe(carpeta_safe, nombre)
        if ruta:
            bandas_rutas[nombre] = ruta
            log(f'    {nombre} → {os.path.basename(ruta)}', 2)
        else:
            log(f'    ✗ No encontrada: {nombre}', 2)

    ruta_scl = encontrar_banda_safe(carpeta_safe, 'SCL')
    if not all(n in bandas_rutas for n, _, _ in CONFIG['bandas']):
        log('  ✗ Faltan bandas — omitiendo fecha', 1)
        return None

    log('  [2/4] Resampleando a 10m...', 1)
    stack_bandas = []
    perfil_ref   = None
    for nombre, _, _ in CONFIG['bandas']:
        datos, perfil = resamplear(bandas_rutas[nombre], CONFIG['resolucion_m'], Resampling.cubic)
        stack_bandas.append(datos[0])
        if perfil_ref is None:
            perfil_ref = perfil
        log(f'    {nombre} ✓', 2)

    datos_scl = None
    if ruta_scl:
        datos_scl, _ = resamplear(ruta_scl, CONFIG['resolucion_m'], Resampling.nearest)
        log('    SCL ✓', 2)

    datos_stack = np.stack(stack_bandas, axis=0)

    log('  [3/4] Máscara SCL...', 1)
    if datos_scl is not None:
        mascara_nube = np.zeros(datos_scl[0].shape, dtype=bool)
        for clase in CONFIG['scl_clases_nube']:
            mascara_nube |= (datos_scl[0] == clase)
        pct = 100 * mascara_nube.sum() / mascara_nube.size
        log(f'    Nubes: {pct:.1f}%', 2)
        for i in range(datos_stack.shape[0]):
            datos_stack[i][mascara_nube] = CONFIG['nodata']

    log('  [4/4] Recortando con shapefile...', 1)
    crs = leer_crs_xml(carpeta_safe) or crs_utm17s()
    log(f'    CRS: {crs.to_epsg() or "UTM17S (WKT)"}', 2)

    try:
        epsg = crs.to_epsg()
        shp  = shapefile_gdf.to_crs(epsg=epsg) if epsg else shapefile_gdf.to_crs(crs.to_wkt())
    except Exception:
        shp = shapefile_gdf

    ruta_temp = ruta_salida.replace('.tif', '_temp.tif')
    perfil_ref['count'] = datos_stack.shape[0]
    p_temp = perfil_ref.copy()
    p_temp['crs'] = crs
    with rasterio.open(ruta_temp, 'w', **p_temp) as dst:
        dst.write(datos_stack)

    geometrias = [g.__geo_interface__ for g in shp.geometry]
    with rasterio.open(ruta_temp) as src:
        datos_clip, t_clip = rio_mask(src, geometrias, crop=True, nodata=CONFIG['nodata'])
        perfil_clip = src.profile.copy()
        perfil_clip.update({
            'height': datos_clip.shape[1], 'width': datos_clip.shape[2],
            'transform': t_clip, 'crs': crs, 'nodata': CONFIG['nodata'],
        })

    os.remove(ruta_temp)

    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
    with rasterio.open(ruta_salida, 'w', **perfil_clip) as dst:
        dst.write(datos_clip.astype('float32'))
        for i, (nombre, _, _) in enumerate(CONFIG['bandas'], 1):
            dst.update_tags(i, name=nombre)

    log(f'  ✅ Guardado → {ruta_salida}', 1)
    return ruta_salida

# ══════════════════════════════════════════════════════════════════
#  MOSAICO FINAL
# ══════════════════════════════════════════════════════════════════

def generar_mosaico(rutas_por_prioridad, carpeta_salida):
    modo = CONFIG['modo_mosaico']
    nombres_modo = {1: 'Simple', 2: 'Normalización estadística', 3: 'Blending'}
    log(f'\n══ Mosaico — Modo {modo}: {nombres_modo[modo]} ══')

    if not OPENCV_DISPONIBLE and CONFIG['relleno_huecos'] == 'opencv':
        log('  ⚠ OpenCV no instalado — usando vecino más cercano', 1)

    nodata         = CONFIG['nodata']
    bandas_mosaico = []
    perfil_final   = None

    for idx, (nombre_banda, num_banda, label) in enumerate(CONFIG['bandas']):
        log(f'\n  [{idx+1}/{len(CONFIG["bandas"])}] {nombre_banda} ({label})', 1)

        _, perfil_ref = leer_banda_tif(rutas_por_prioridad[0], num_banda)

        if modo == 1:
            mosaico = mosaico_simple(rutas_por_prioridad, num_banda, perfil_ref, nodata)
        elif modo == 2:
            mosaico = mosaico_normalizado(rutas_por_prioridad, num_banda, perfil_ref, nodata)
        elif modo == 3:
            mosaico = mosaico_blending(rutas_por_prioridad, num_banda, perfil_ref, nodata, CONFIG['blending_px'])

        huecos = (mosaico == nodata).sum()
        if huecos > 0 and CONFIG['relleno_huecos']:
            log(f'    Rellenando {huecos:,} huecos restantes...', 2)
            mosaico = rellenar_huecos(mosaico, nodata)
            huecos_post = (mosaico == nodata).sum()
            log(f'    Huecos tras relleno: {huecos_post:,}', 2)

        bandas_mosaico.append((nombre_banda, mosaico))
        if perfil_final is None:
            perfil_final = perfil_ref
        log(f'    ✓ {nombre_banda} completada', 2)

    log(f'\n  Apilando {len(bandas_mosaico)} bandas...', 1)
    stack = np.stack([d for _, d in bandas_mosaico], axis=0)

    ruta_salida = os.path.join(carpeta_salida, CONFIG['nombre_salida'])
    perfil_out  = perfil_final.copy()
    perfil_out.update({
        'count': len(bandas_mosaico), 'dtype': 'float32',
        'nodata': nodata, 'compress': 'lzw',
        'driver': 'GTiff', 'bigtiff': 'IF_SAFER',
    })
    with rasterio.open(ruta_salida, 'w', **perfil_out) as dst:
        for i, (nombre, _) in enumerate(bandas_mosaico, 1):
            dst.write(stack[i-1], i)
            dst.update_tags(i, name=nombre)

    log(f'\n  ✅ Mosaico → {ruta_salida}', 1)

    if CONFIG['calcular_indices']:
        log('\n══ Calculando índices espectrales ══')
        bandas_dict = {
            nombre: stack[i] for i, (nombre, _) in enumerate(bandas_mosaico)
        }
        for nombre_idx in CONFIG['indices']:
            log(f'  {nombre_idx}...', 1)
            indice = calcular_indice(nombre_idx, bandas_dict, nodata)
            if indice is not None:
                guardar_indice(nombre_idx, indice, perfil_final, carpeta_salida)

    return ruta_salida

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    print('╔══════════════════════════════════════════════════╗')
    print('║   PIPELINE SENTINEL-2 v4.2 (con MNDWI)          ║')
    print('╚══════════════════════════════════════════════════╝\n')

    os.makedirs(os.path.join(CONFIG['carpeta_salida'], 'por_fecha'), exist_ok=True)

    log('Cargando shapefile...')
    shapefile_gdf = gpd.read_file(CONFIG['shapefile'])
    log(f'  CRS: {shapefile_gdf.crs} | Geometrías: {len(shapefile_gdf)}')

    log('\nBuscando productos .SAFE...')
    carpetas_safe = sorted(glob.glob(os.path.join(CONFIG['carpeta_safe'], '*.SAFE')))
    if not carpetas_safe:
        print('✗ No se encontraron .SAFE en:', CONFIG['carpeta_safe'])
        return

    mapa_fechas = {}
    for carpeta in carpetas_safe:
        nombre = os.path.basename(carpeta)
        for p in nombre.split('_'):
            if len(p) == 15 and p[:8].isdigit():
                fecha = p[:8]
                mapa_fechas[fecha] = carpeta
                log(f'  {fecha} → {nombre}')
                break

    fechas_ordenadas = [f for f in CONFIG['prioridad_fechas'] if f in mapa_fechas]
    for f in mapa_fechas:
        if f not in fechas_ordenadas:
            fechas_ordenadas.append(f)
    log(f'\nPrioridad: {" > ".join(fechas_ordenadas)}')

    rutas_procesadas = []
    for fecha in fechas_ordenadas:
        ruta = procesar_fecha(mapa_fechas[fecha], fecha, shapefile_gdf, CONFIG['carpeta_salida'])
        if ruta:
            rutas_procesadas.append(ruta)

    if not rutas_procesadas:
        print('\n✗ No se procesó ninguna fecha.')
        return

    generar_mosaico(rutas_procesadas, CONFIG['carpeta_salida'])

    print('\n╔══════════════════════════════════════════════════╗')
    print('║   PIPELINE COMPLETADO                            ║')
    print('╚══════════════════════════════════════════════════╝')

if __name__ == '__main__':
    main()