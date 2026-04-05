# FICHA TÉCNICA — SEMANA 1
## Setup del proyecto + pipeline Sentinel-2 para el Parque Nacional Podocarpus

---

## OBJETIVO DE LA SEMANA ✅ COMPLETADO

Construir un pipeline completo y reutilizable de preprocesamiento Sentinel-2 para el Parque Nacional Podocarpus, desde la identificación de tiles hasta la generación de índices espectrales reclasificados y mapas temáticos profesionales.

---

## ENTREGABLES COMPLETADOS

| Entregable | Script | Estado |
|-----------|--------|--------|
| Identificación de tiles Sentinel-2 desde WKT | `00_identificar_tiles.py` | ✅ |
| Búsqueda y descarga de imágenes L2A (CDSE) | `01_buscar_y_descargar.py` | ✅ |
| Resampleo a 10m, máscara de nubes (SCL), recorte con shapefile | `02_pipeline_sentinel2.py` v4.2 | ✅ |
| Mosaico multitemporal (4 fechas, modo normalización estadística) | `02_pipeline_sentinel2.py` v4.2 | ✅ |
| Relleno de huecos con OpenCV inpaint (fallback a vecino más cercano) | `02_pipeline_sentinel2.py` v4.2 | ✅ |
| 6 índices espectrales en float32: NDVI, NDWI, MNDWI, SAVI, EVI, NBR | `02_pipeline_sentinel2.py` v4.2 | ✅ |
| Reclasificación en 4 clases con umbrales ajustados a Podocarpus | `03_reclasificacion_indices.py` v3.1 | ✅ |
| Reportes CSV de áreas por clase (ha, km², %) | `03_reclasificacion_indices.py` v3.1 | ✅ |
| Estilos `.qml` para apertura directa con colores en QGIS | `03_reclasificacion_indices.py` v3.1 | ✅ |
| Mapas temáticos: impreso A3, Instagram, presentación | `04_generar_mapa.py` v4.0 | ✅ |
| Shapefile del PN Podocarpus verificado y en EPSG:4326 | QGIS | ✅ |
| Repositorio GitHub estructurado con README | Git | ✅ |

---

## DATOS DE ENTRADA UTILIZADOS

- **Área de estudio:** Parque Nacional Podocarpus (límite MAATE, reproyectado a EPSG:4326)
- **Imágenes descargadas:** 4 fechas Sentinel-2 L2A — 20240704, 20240912, 20241002, 20241111
- **Tiles cubiertos:** T17MPQ, T17MPR (y adyacentes según intersección con el polígono)
- **Bandas utilizadas:** B2, B3, B4, B8, B11, B12 + SCL (máscara de nubes)

---

## ÍNDICES CALCULADOS Y UMBRALES

| Índice | Fórmula | Clase 1 | Clase 2 | Clase 3 | Clase 4 |
|--------|---------|---------|---------|---------|---------|
| NDVI | (NIR−Red)/(NIR+Red) | <0 Agua/nieve | 0–0.2 Suelo | 0.2–0.5 Veg. escasa | >0.5 Veg. densa |
| NDWI | (Green−NIR)/(Green+NIR) | <0 Suelo seco | 0–0.2 Hum. baja | 0.2–0.5 Hum. mod. | >0.5 Agua |
| MNDWI | (Green−SWIR1)/(Green+SWIR1) | <0 Suelo seco | 0–0.1 Hum. baja | 0.1–0.2 Hum. mod. | >0.2 Agua abierta |
| SAVI | ((NIR−Red)/(NIR+Red+0.5))×1.5 | <0 Agua/sombras | 0–0.2 Suelo | 0.2–0.55 Veg. joven | >0.55 Bosque denso |
| EVI | 2.5×(NIR−Red)/(NIR+6Red−7.5Blue+1) | <0 Nubes/nieve | 0–0.2 Urbano/suelo | 0.2–0.4 Veg. moderada | >0.4 Selva/biomasa |
| NBR | (NIR−SWIR2)/(NIR+SWIR2) | <0 Área quemada | 0–0.2 Quemado leve | 0.2–0.4 Recuperación | >0.4 Veg. sana |

> **Nota:** Se añadió MNDWI en reemplazo parcial de NDWI porque la normalización estadística del mosaico (modo 2) alteraba la relación Green/NIR produciendo valores negativos en cuerpos de agua. MNDWI usa SWIR1 y es mucho más robusto.

---

## ERRORES ENCONTRADOS Y SOLUCIONES APLICADAS

| Error | Causa | Solución |
|-------|-------|---------|
| Conflicto PROJ con PostgreSQL | Variables de entorno sobrescritas | Bloque al inicio del script reasigna `PROJ_DATA` / `PROJ_LIB` a `rasterio/proj_data` |
| Bandas no encontradas en `.SAFE` | Variación en estructura de carpetas S2 | Búsqueda con patrones `glob` múltiples (`**/IMG_DATA/R*m/*.jp2`) |
| SCL a 20m sin alinear con bandas 10m | Diferente resolución nativa | Resampleo de SCL con `Resampling.nearest` a 10m |
| Huecos en mosaico | Nubes en todas las fechas | `cv2.inpaint` (Telea); fallback a `scipy` vecino más cercano |
| NDWI negativo en lagunas | Normalización estadística del mosaico | Implementación de MNDWI (más robusto, usa SWIR1) |
| Índices guardados ×10000 en int16 | `guardar_indice` escalaba los datos | Guardado en float32 sin escalar (rango correcto −1 a 1) |
| Doble división por 10000 | Bandas ya en reflectancia desde el mosaico | Verificación de origen; división única dentro de `calcular_indice` |
| Geometrías inválidas en shapefile | Archivos MAATE con autointersecciones | `make_valid()` + `buffer(0)` |
| Colormap invisible en QGIS | Compresión LZW interfería | Guardar sin compresión + generar `.qml` externo |
| `axhline` error en presentación | `transform` no permitido en ese contexto | Reemplazado por `ax.plot()` con `transform=ax.transAxes` |
| Rangos de reclasificación sin píxeles en clase 3 | Umbrales genéricos no ajustados a Podocarpus | Ajuste basado en estadísticas reales del raster |

---

## CONFIGURACIÓN FINAL DEL PIPELINE

```python
CONFIG = {
    'carpeta_safe'    : r'F:\geodatos-ecuador\datos\raw\Podocarpus',
    'shapefile'       : r'F:\geodatos-ecuador\datos\aoi\Podocarpus\podocarpus_wgs84.shp',
    'carpeta_salida'  : r'F:\geodatos-ecuador\datos\processed\Podocarprocessed',
    'prioridad_fechas': ['20240704', '20240912', '20241002', '20241111'],
    'modo_mosaico'    : 2,         # normalización estadística
    'relleno_huecos'  : 'opencv',  # Telea inpainting
    'calcular_indices': True,
    'indices'         : ['NDVI', 'NDWI', 'MNDWI', 'SAVI', 'EVI', 'NBR'],
}
```

---

## ARCHIVOS GENERADOS EN `datos/processed/`

```
datos/processed/Podocarprocessed/
├── mosaico_sentinel2_multibanda.tif    # 6 bandas, float32, 10m
├── por_fecha/
│   ├── 20240704_procesado.tif
│   ├── 20240912_procesado.tif
│   ├── 20241002_procesado.tif
│   └── 20241111_procesado.tif
├── indices/
│   ├── NDVI.tif, NDWI.tif, MNDWI.tif, SAVI.tif, EVI.tif, NBR.tif
│   ├── NDVI_clases.tif  + NDVI_clases.qml
│   ├── ...  (idem para cada índice)
│   ├── NDVI_reporte.csv, ... (reporte por índice)
│   └── reporte_indices_global.csv
└── clasificacion/
    └── mapas/
        ├── NDVI_impreso.png, NDVI_instagram.png, NDVI_presentacion.png
        └── ... (idem para cada índice)
```

---

## LECCIONES APRENDIDAS

- La banda SCL de Sentinel-2 L2A es muy útil para enmascarar nubes, pero requiere resampleo a 10m y selección cuidadosa de las clases enmascaradas.
- El mosaico por normalización estadística (modo 2) reduce significativamente los parches radiométricos entre fechas.
- OpenCV inpaint es excelente para rellenar huecos pequeños, pero no debe usarse en áreas grandes (>1000 píxeles continuos) porque inventa textura.
- MNDWI es más robusto que NDWI para detectar agua cuando el mosaico multitemporal aplica normalización estadística.
- Es fundamental verificar visualmente en QGIS cada paso del procesamiento para detectar errores de alineación, reclasificación o escala.
- Los scripts deben guardar índices en float32 sin escalar para preservar el rango −1 a 1 y evitar errores en etapas posteriores.

---

## CHECKLIST FINAL SEMANA 1 ✅

- [x] Repositorio GitHub público con README profesional
- [x] Estructura de carpetas creada y commiteada
- [x] Shapefile PN Podocarpus descargado, verificado y en EPSG:4326
- [x] 4 imágenes S2 L2A descargadas (julio–noviembre 2024)
- [x] Pipeline ejecutado sin errores (4 fechas procesadas)
- [x] 6 índices calculados y verificados en QGIS (float32, rango −1 a 1)
- [x] Reclasificación en 4 clases con umbrales ajustados a Podocarpus
- [x] Reportes CSV de áreas por índice y reporte global
- [x] Estilos `.qml` para apertura directa con colores en QGIS
- [x] Mapas temáticos en 3 formatos (impreso, Instagram, presentación)
- [x] Documentación de errores comunes y soluciones

---

*Ficha actualizada — abril de 2026. Pipeline reutilizable para cualquier área de Ecuador.*
