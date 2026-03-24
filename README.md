# Geodatos Abiertos Ecuador 🗺

**Cartografía temática de libre acceso** generada con imágenes satelitales Sentinel-1 y Sentinel-2 para Ecuador — cobertura vegetal, deforestación, gestión de riesgos y vulnerabilidad territorial.

---

## Sobre el proyecto

Este repositorio contiene datos geoespaciales procesados, scripts de análisis y metodologías documentadas para la generación de información territorial de acceso libre en Ecuador. Todos los productos son reproducibles a partir de datos abiertos (Copernicus, USGS, MAATE, INEC).

**Autor:** Daniel Estrada — Ingeniero en Geología y Minas · Especialista SIG  
**Contacto:** daniel.geo.consultor@proton.me  
**Licencia datos:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
**Licencia código:** MIT

---

## Estructura del repositorio

```
geodatos-ecuador/
│
├── 01_cobertura_vegetal/          ← Fase 1: Podocarpus y Loja
│   ├── podocarpus_2024/
│   │   ├── README.md
│   │   ├── mapa_cobertura_2024.png
│   │   ├── podocarpus_ndvi_2024.tif
│   │   └── metodologia.md
│   └── loja_uso_suelo_2024/
│
├── 02_deforestacion/              ← Fase 2: Provincial y nacional
│   ├── podocarpus_cambio_2015_2024/
│   ├── parques_nacionales_snap/
│   └── provincial_ecuador/
│
├── 03_riesgos/                    ← Fase 3: Inundaciones y deslizamientos
│   ├── inundaciones_loja/
│   ├── deslizamientos_andes_sur/
│   └── amenaza_nacional/
│
├── 04_vulnerabilidad/             ← Fase 4: Exposición y riesgo
│   ├── exposicion_poblacional/
│   └── atlas_riesgo_loja/
│
├── scripts/                       ← Scripts reutilizables
│   ├── 00_buscar_descargar_s2.py
│   ├── 01_preprocesar_sentinel2.py
│   ├── 02_clasificar_cobertura.py    ← próximamente
│   └── utils/
│
├── docs/
│   ├── fuentes_datos.md
│   ├── metodologia_general.md
│   └── glosario.md
│
└── README.md                      ← este archivo
```

---

## Productos disponibles

### Cobertura vegetal y bosques

| Producto | Área | Año | Resolución | Descargar |
|----------|------|-----|------------|-----------|
| Cobertura vegetal Podocarpus | PN Podocarpus | 2024 | 10m | *próximamente* |
| Cambio de cobertura 2015–2024 | PN Podocarpus | 2015–2024 | 10m | *próximamente* |
| Uso de suelo cantón Loja | Loja | 2024 | 10m | *próximamente* |

### Deforestación

| Producto | Área | Período | Resolución | Descargar |
|----------|------|---------|------------|-----------|
| Deforestación interanual | Provincia Loja | 2000–2024 | 30m | *próximamente* |
| Cobertura forestal SNAP | Ecuador | 2024 | 10m | *próximamente* |

### Gestión de riesgos

| Producto | Área | Método | Resolución | Descargar |
|----------|------|--------|------------|-----------|
| Susceptibilidad inundaciones | Cantón Loja | TWI + histórico | 30m | *próximamente* |
| Susceptibilidad deslizamientos | Andes Sur | LSI multicriterio | 30m | *próximamente* |

---

## Fuentes de datos

| Fuente | Datos | Acceso |
|--------|-------|--------|
| [Copernicus Data Space](https://dataspace.copernicus.eu/) | Sentinel-1, Sentinel-2 | Gratuito |
| [USGS Earth Explorer](https://earthexplorer.usgs.gov/) | Landsat 8/9 | Gratuito |
| [Copernicus DEM](https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model) | DEM 30m | Gratuito |
| [MAATE Ecuador](https://geodata.environment.ec/) | Límites SNAP, cobertura oficial | Gratuito |
| [IGM Ecuador](https://www.igm.gob.ec/) | Cartografía base | Gratuito |
| [INAMHI](https://www.inamhi.gob.ec/) | Datos climáticos e hidrológicos | Gratuito |
| [INEC](https://www.ecuadorencifras.gob.ec/) | Censo 2022, límites cantonales | Gratuito |
| [IGEPN](https://www.igepn.edu.ec/) | Sismicidad, vulcanismo | Gratuito |

---

## Cómo usar los scripts

### Requisitos

```bash
pip install rasterio numpy geopandas shapely matplotlib fiona pyproj requests tqdm
```

### Flujo básico

```bash
# 1. Buscar y listar imágenes disponibles
python scripts/00_buscar_descargar_s2.py

# 2. (Descarga manual desde Copernicus Browser si prefieres)
# https://browser.dataspace.copernicus.eu

# 3. Preprocesar imagen descargada
python scripts/01_preprocesar_sentinel2.py

# 4. Clasificar cobertura (requiere puntos de entrenamiento en QGIS)
# python scripts/02_clasificar_cobertura.py
```

### Configuración mínima

Edita el bloque `CONFIG` en `01_preprocesar_sentinel2.py`:

```python
CONFIG = {
    "safe_dir":        Path("datos/raw/S2A_MSIL2A_YYYYMMDD.SAFE"),
    "aoi_shp":         Path("datos/aoi/podocarpus_limite.shp"),
    "output_dir":      Path("datos/procesados"),
    "resolucion":      10,
    "nombre_proyecto": "podocarpus_2024",
}
```

---

## Metodología

Todos los productos siguen este flujo de procesamiento:

```
Descarga S2 L2A (Copernicus)
    ↓
Corrección atmosférica (incluida en L2A — BOA reflectance)
    ↓
Recorte al AOI + reproyección UTM Zone 17S
    ↓
Cálculo de índices espectrales (NDVI, EVI, NDWI, BSI)
    ↓
Clasificación supervisada (QGIS SCP / Python scikit-learn)
    ↓
Validación (matriz de confusión, puntos de campo)
    ↓
Cartografía final + exportación
    ↓
Publicación datos abiertos (GitHub + Zenodo)
```

Documentación detallada: [docs/metodologia_general.md](docs/metodologia_general.md)

---

## Citar este trabajo

Si usas estos datos en tu investigación o trabajo:

```
Estrada, D. (2024). Geodatos Abiertos Ecuador: Cartografía temática con
Sentinel-1/2. GitHub. https://github.com/danielestrada/geodatos-ecuador
Licencia CC BY 4.0.
```

---

## Contribuciones

Las contribuciones son bienvenidas. Si tienes datos, puntos de validación de campo o mejoras a los scripts, abre un issue o pull request.

---

*Proyecto en desarrollo activo · Actualizado semanalmente*
