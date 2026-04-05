# Geodatos Abiertos Ecuador 🗺️

**Cartografía temática de libre acceso** generada con imágenes satelitales Sentinel-2 para Ecuador — cobertura vegetal, deforestación, gestión de riesgos y vulnerabilidad territorial.

---

## 👤 Autor y contacto

**Daniel Estrada** – Ingeniero en Geología y Minas · Especialista SIG  
📧 daniel.geo.consultor@proton.me  
🔗 [GitHub](https://github.com/danielestrada/geodatos-ecuador)  
📄 Licencia datos: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
💻 Licencia código: MIT

---

## 📌 Estado actual del proyecto

✅ **Semana 1 completada** — Pipeline completo: descarga, preprocesamiento, mosaico multitemporal, 6 índices espectrales, reclasificación y reportes CSV.  
✅ **Semana 2 completada** — Generación de mapas temáticos profesionales en tres formatos (impreso, Instagram, presentación).  
🔄 **Semana 3 en curso** — Clasificación supervisada de cobertura vegetal (Random Forest).  
📅 **Próximo hito:** Mapa de cobertura vegetal del Parque Nacional Podocarpus (2024).

**Entregables completados:**
- Identificación automática de tiles Sentinel-2 desde un polígono WKT
- Descarga de imágenes L2A desde CDSE con autenticación y reanudación
- Pipeline de preprocesamiento: resampleo a 10m, máscara de nubes (SCL), recorte con shapefile
- Mosaico multitemporal con 3 modos (simple, normalización estadística, blending)
- 6 índices espectrales en float32: NDVI, NDWI, MNDWI, SAVI, EVI, NBR
- Reclasificación en 4 clases temáticas con umbrales ajustados a Podocarpus
- Reportes CSV de áreas por clase (ha, km², porcentaje)
- Estilos `.qml` para apertura directa con colores en QGIS
- Mapas temáticos profesionales: impreso A3, Instagram 1080×1080 y presentación 1920×1080

---

## 📁 Estructura del repositorio

```
geodatos-ecuador/
│
├── 01_cobertura_vegetal/              # Próximamente: resultados sem. 3
├── 02_deforestacion/                  # Próximamente: sem. 7-9
├── 03_riesgos/                        # Próximamente: sem. 14-20
├── 04_vulnerabilidad/                 # Próximamente: sem. 21-26
│
├── scripts/
│   ├── 00_identificar_tiles.py        # Identifica tiles S2 desde un WKT
│   ├── 01_buscar_y_descargar.py       # Descarga imágenes L2A (CDSE)
│   ├── 02_pipeline_sentinel2.py       # Pipeline principal v4.2
│   ├── 03_reclasificacion_indices.py  # Reclasificación y áreas v3.1
│   ├── 04_generar_mapa.py             # Generación de mapas temáticos v4.0
│   └── utils/                         # Módulos auxiliares opcionales
│
├── datos/                             # Ignorados por git (.gitignore)
│   ├── aoi/
│   │   └── Podocarpus/                # Shapefile del área de estudio
│   │       └── podocarpus_wgs84.shp   # (+ .shx, .dbf, .prj) — CRS: EPSG:4326
│   │
│   ├── raw/
│   │   ├── Podocarpus/                # Productos .SAFE (4 fechas)
│   │   │   ├── S2B_...20240704...SAFE
│   │   │   ├── S2B_...20240912...SAFE
│   │   │   ├── S2B_...20241002...SAFE
│   │   │   └── S2B_...20241111...SAFE
│   │   └── Sentinel-2-Shapefile-Index-master/  # Grilla MGRS (para 00_identificar_tiles.py)
│   │
│   └── processed/
│       └── Podocarprocessed/          # Raíz de salida del pipeline
│           ├── por_fecha/             # Recortes procesados por fecha
│           ├── indices/               # GeoTIFF por índice (float32, rango -1 a 1)
│           └── clasificacion/
│               └── mapas/             # Mapas generados por 04_generar_mapa.py
│
├── docs/
│   ├── metodologia_general.md
│   ├── errores_comunes.md
│   └── glosario.md
│
├── FICHA_SEMANA1.md
├── FICHA_SEMANA2.md
└── README.md
```

---

## 🔧 Flujo de procesamiento completo

### 1. Identificar los tiles Sentinel-2

```bash
python scripts/00_identificar_tiles.py --area datos/aoi/area.wkt --guardar-tiles tiles.txt
```

Lee un polígono en formato WKT, cruza con la grilla MGRS ubicada en `datos/raw/Sentinel-2-Shapefile-Index-master/` y genera la lista de tiles con sus áreas de intersección (ej. `T17MPQ`, `T17MPR`).

### 2. Buscar y descargar imágenes L2A

```bash
python scripts/01_buscar_y_descargar.py --tiles-file tiles.txt \
    --fecha-inicio 2024-07-01 --fecha-fin 2024-09-30 --nubes 30
```

Autenticación mediante `.env` (`CDSE_USER`, `CDSE_PASS`). Descarga interactiva con barra de progreso, reanudación y renovación automática de token (error 401). Los `.SAFE` se guardan en `datos/raw/Podocarpus/`.

### 3. Pipeline principal: mosaico + índices

```bash
python scripts/02_pipeline_sentinel2.py
```

Editar el bloque `CONFIG` antes de ejecutar:

```python
CONFIG = {
    'carpeta_safe'   : r'F:\geodatos-ecuador\datos\raw\Podocarpus',
    'shapefile'      : r'F:\geodatos-ecuador\datos\aoi\Podocarpus\podocarpus_wgs84.shp',
    'carpeta_salida' : r'F:\geodatos-ecuador\datos\processed\Podocarprocessed',
    'prioridad_fechas': ['20240704', '20240912', '20241002', '20241111'],
    'modo_mosaico'   : 2,        # 1=simple, 2=normalización, 3=blending
    'relleno_huecos' : 'opencv', # 'opencv' o 'vecino'
    'calcular_indices': True,
    'indices'        : ['NDVI', 'NDWI', 'MNDWI', 'SAVI', 'EVI', 'NBR'],
}
```

El script procesa 4 fechas con máscara SCL, resampleo a 10m, recorte al shapefile, mosaico y cálculo de 6 índices en float32.

**Modos de mosaico:**

| Modo | Nombre | Cuándo usarlo |
|------|--------|---------------|
| 1 | Simple | Pocas nubes, fechas similares |
| 2 | Normalización estadística | Recomendado — elimina parches entre fechas |
| 3 | Blending | Transiciones muy suaves en bordes |

### 4. Reclasificación y cálculo de áreas

```bash
python scripts/03_reclasificacion_indices.py
```

Lee desde `datos/processed/Podocarprocessed/indices/`. Genera por cada índice: raster de clases `uint8`, estilo `.qml` para QGIS y reporte CSV. Salida en `datos/processed/Podocarprocessed/clasificacion/`.

### 5. Generación de mapas temáticos

```bash
# Todos los índices, todos los formatos
python scripts/04_generar_mapa.py

# Solo MNDWI en formato Instagram
python scripts/04_generar_mapa.py --indice MNDWI --formato instagram

# Impreso vertical
python scripts/04_generar_mapa.py --orientacion vertical
```

Los mapas se guardan en `datos/processed/Podocarprocessed/clasificacion/mapas/`.

---

## 📊 Índices espectrales

| Índice | Fórmula | Aplicación |
|--------|---------|------------|
| NDVI | (NIR − Red) / (NIR + Red) | Vigor vegetal, cobertura verde |
| NDWI | (Green − NIR) / (Green + NIR) | Contenido de agua en vegetación |
| MNDWI | (Green − SWIR1) / (Green + SWIR1) | Agua abierta (más robusto que NDWI) |
| SAVI | ((NIR − Red) / (NIR + Red + L)) × (1+L) | NDVI corregido por brillo de suelo |
| EVI | 2.5 × (NIR − Red) / (NIR + 6·Red − 7.5·Blue + 1) | Alta biomasa, no se satura |
| NBR | (NIR − SWIR2) / (NIR + SWIR2) | Detección de áreas quemadas |

**Tabla de clases (umbrales ajustados a Podocarpus):**

| Índice | Clase 1 | Clase 2 | Clase 3 | Clase 4 |
|--------|---------|---------|---------|---------|
| NDVI | < 0 Agua/nieve | 0–0.2 Suelo | 0.2–0.5 Veg. escasa | > 0.5 Veg. densa |
| MNDWI | < 0 Suelo seco | 0–0.1 Humedad baja | 0.1–0.2 Humedad mod. | > 0.2 Agua abierta |
| SAVI | < 0 Agua/sombras | 0–0.2 Suelo | 0.2–0.55 Veg. joven | > 0.55 Bosque denso |
| EVI | < 0 Nubes/nieve | 0–0.2 Urbano/suelo | 0.2–0.4 Veg. moderada | > 0.4 Selva/biomasa alta |
| NBR | < 0 Área quemada | 0–0.2 Quemado leve | 0.2–0.4 En recuperación | > 0.4 Veg. sana |

---

## 🖼️ Formatos de mapa generados

| Formato | Resolución | Uso |
|---------|-----------|-----|
| Impreso A3 | 300 dpi | Informes técnicos, publicación |
| Instagram | 1080×1080 px | Difusión en redes sociales |
| Presentación | 1920×1080 px | Diapositivas con panel de estadísticas |

---

## 🐞 Errores comunes y soluciones

| Error | Causa | Solución |
|-------|-------|---------|
| Conflicto PROJ / PostgreSQL | Variables de entorno sobrescritas | Bloque al inicio del script reasigna `PROJ_DATA` y `PROJ_LIB` a `rasterio/proj_data` |
| Bandas no encontradas en `.SAFE` | Cambios en estructura de carpetas S2 | Búsqueda con múltiples patrones `glob` (`**/IMG_DATA/R*m/*.jp2`) |
| SCL a 20m desalineada | Resolución diferente a bandas 10m | Resampleo con `Resampling.nearest` |
| Huecos en mosaico | Nubes persistentes en todas las fechas | `cv2.inpaint` (Telea) — fallback a vecino más cercano |
| NDWI negativo en lagunas | Normalización estadística alteraba relación B3/B8 | Implementación de MNDWI (usa SWIR1, más robusto) |
| Índices escalados ×10000 | `guardar_indice` guardaba en int16 | Guardado en float32 sin escalar (rango −1 a 1) |
| Geometrías inválidas en shapefile | Archivos MAATE con autointersecciones | `make_valid` + `buffer(0)` |
| Colormap invisible en QGIS | Compresión LZW interfería | Guardado sin compresión + generación de `.qml` externo |
| `MemoryError` en imágenes grandes | Escena completa cargada en RAM | Recorte previo con shapefile; procesamiento en bloques o a 20m |
| Token expirado en descarga | Token CDSE válido solo 10 min | Captura de error 401 y renovación automática |

---

## 📦 Instalación

```bash
git clone https://github.com/danielestrada/geodatos-ecuador.git
cd geodatos-ecuador

python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

**`requirements.txt`:**

```text
rasterio
numpy
geopandas
pandas
scipy
opencv-python
requests
tqdm
python-dotenv
shapely
scikit-learn
matplotlib
```

> En Windows se necesita Git Bash para `unzip` o instalar 7-Zip y agregarlo al PATH.

---

## 🚀 Cronograma del proyecto (26 semanas)

### Fase 1 — Fundación y cobertura vegetal (Semanas 1–6)

| Sem | Producto | Estado |
|-----|----------|--------|
| 1 | Setup + pipeline S2 Podocarpus (tiles, descarga, mosaico, índices, reclasificación) | ✅ Completado |
| 2 | Mapas temáticos profesionales (impreso, Instagram, presentación) | ✅ Completado |
| 3 | Clasificación supervisada de cobertura vegetal (Random Forest) | 🔄 En curso |
| 4 | Suelo desnudo y frontera agropecuaria (BSI, NDVI bajo) | Pendiente |
| 5 | Uso de suelo cantón Loja (datos censales + clasificación) | Pendiente |
| 6 | Hidrología básica provincia Loja (redes de drenaje, TWI, microcuencas) | Pendiente |

### Fase 2 — Bosques y deforestación (Semanas 7–13)

| Sem | Producto | Estado |
|-----|----------|--------|
| 7 | Deforestación interanual Loja 2000–2024 (Landsat + Sentinel-2) | Pendiente |
| 8 | Cobertura forestal todos los parques SNAP | Pendiente |
| 9–10 | Deforestación histórica por parque y por provincia | Pendiente |
| 11–12 | Regeneración natural y avance frontera agrícola Amazonía (SAR) | Pendiente |
| 13 | **HITO:** Atlas Forestal Ecuador v1.0 | Pendiente |

### Fase 3 — Gestión de riesgos (Semanas 14–20)

| Sem | Producto | Estado |
|-----|----------|--------|
| 14–15 | DEM, modelo hidrológico, susceptibilidad a inundaciones (Loja) | Pendiente |
| 16–17 | Susceptibilidad a deslizamientos Andes Sur + detección SAR | Pendiente |
| 18–20 | Mapas de inundación provincial + amenaza multicriterio nacional | Pendiente |

### Fase 4 — Vulnerabilidad y consolidación (Semanas 21–26)

| Sem | Producto | Estado |
|-----|----------|--------|
| 21–23 | Vulnerabilidad socioeconómica + exposición poblacional | Pendiente |
| 24–26 | Atlas de riesgos Ecuador v1.0 + publicación final | Pendiente |

---

## 📚 Fuentes de datos

- **Imágenes Sentinel-2 L2A:** [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/)
- **Límites áreas protegidas:** SNAPEcuador (MAATE)
- **DEM:** Copernicus GLO-90 (para corrección topográfica futura)
- **Grilla MGRS Sentinel-2:** [Sentinel-2 Shapefile Index](https://github.com/justinelliotmeyers/Sentinel-2-Shapefile-Index)

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Si deseas mejorar los scripts, agregar nuevos índices o corregir errores, abre un issue o un pull request.

---

*Proyecto en desarrollo activo — Actualizado a abril de 2026 (Semana 3 en curso)*
