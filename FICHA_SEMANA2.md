# FICHA TÉCNICA — SEMANA 2
## Generación de mapas temáticos profesionales — Parque Nacional Podocarpus

---

## OBJETIVO DE LA SEMANA ✅ COMPLETADO

Desarrollar un script de generación automática de mapas temáticos a partir de los índices espectrales reclasificados, con salida en tres formatos profesionales: impreso A3, Instagram y presentación.

---

## ENTREGABLES COMPLETADOS

| Entregable | Script | Estado |
|-----------|--------|--------|
| Mapa impreso A3 (horizontal/vertical, 300 dpi) | `04_generar_mapa.py` v4.0 | ✅ |
| Mapa Instagram (1080×1080 px, fondo oscuro) | `04_generar_mapa.py` v4.0 | ✅ |
| Mapa presentación (1920×1080 px, panel estadísticas) | `04_generar_mapa.py` v4.0 | ✅ |
| Paletas de color para 6 índices (NDVI, NDWI, MNDWI, SAVI, EVI, NBR) | `04_generar_mapa.py` v4.0 | ✅ |
| Pie de página embebido en la imagen (3 líneas) | `04_generar_mapa.py` v4.0 | ✅ |
| Escala y norte adaptables por formato (color automático) | `04_generar_mapa.py` v4.0 | ✅ |
| Leyenda reposicionable por parámetro | `04_generar_mapa.py` v4.0 | ✅ |

---

## USO DEL SCRIPT

```bash
# Todos los índices, todos los formatos
python scripts/04_generar_mapa.py

# Solo un índice y un formato
python scripts/04_generar_mapa.py --indice MNDWI --formato instagram

# Impreso en orientación vertical
python scripts/04_generar_mapa.py --orientacion vertical
```

Los mapas se guardan automáticamente en `datos/processed/Podocarprocessed/clasificacion/mapas/`.

---

## FORMATOS DE SALIDA

| Formato | Resolución | Fondo | Texto | Uso |
|---------|-----------|-------|-------|-----|
| Impreso A3 | 300 dpi | Claro | Negro | Informes técnicos, publicación |
| Instagram | 1080×1080 px | Oscuro | Blanco | Redes sociales |
| Presentación | 1920×1080 px | Oscuro | Blanco | Diapositivas + panel de estadísticas |

> La escala y el norte cambian de color automáticamente según el fondo (claro/oscuro), pero se pueden forzar con los parámetros `color_escala` y `color_norte`.

---

## PALETAS POR ÍNDICE

| Índice | Clase 1 | Clase 2 | Clase 3 | Clase 4 |
|--------|---------|---------|---------|---------|
| NDVI | Agua/nieve | Suelo desnudo | Veg. escasa | Veg. densa |
| NDWI | Suelo seco | Humedad baja | Humedad mod. | Agua abierta |
| MNDWI | Suelo/urbano (#EF9F27) | Humedad baja (#85B7EB) | Humedad mod. (#378ADD) | Agua (#042C53) |
| SAVI | Agua/sombras | Suelo expuesto | Veg. joven | Bosque denso |
| EVI | Nubes/nieve | Urbano/suelo | Veg. moderada | Selva/biomasa |
| NBR | Área quemada | Quemado leve | Recuperación | Veg. sana |

---

## ERRORES ENCONTRADOS Y SOLUCIONES

| Error | Causa | Solución |
|-------|-------|---------|
| Padding (margen) alrededor del shapefile | `set_xlim` con offset | Cambiado a `ax_mapa.set_xlim(b[0], b[2])` — ajuste exacto al polígono |
| Borde del área de estudio visible | `gdf.boundary.plot()` activo | Línea comentada; se descomenta si se quiere borde negro |
| `axhline` error en formato presentación | `transform` no permitido en `axhline` | Reemplazado por `ax.plot()` con `transform=ax.transAxes` |
| MNDWI no disponible en el script | Solo existían 5 índices originales | Se añadió entrada completa en `PALETAS` con colores, etiquetas y fórmula |
| Pie de página fuera de la imagen | Coordenadas absolutas dependientes del tamaño | Reemplazado por `fig.text()` con coordenadas relativas a la figura |

---

## ARCHIVOS GENERADOS EN `datos/processed/mapas/`

```
datos/processed/Podocarprocessed/clasificacion/mapas/
├── NDVI_impreso.png
├── NDVI_instagram.png
├── NDVI_presentacion.png
├── NDWI_impreso.png
├── NDWI_instagram.png
├── NDWI_presentacion.png
├── MNDWI_impreso.png
├── MNDWI_instagram.png
├── MNDWI_presentacion.png
└── ... (idem para SAVI, EVI, NBR)
```

---

## LECCIONES APRENDIDAS

- Los formatos de salida tienen necesidades muy distintas: el impreso prioriza legibilidad y resolución; Instagram prioriza impacto visual con fondo oscuro y saturación aumentada (+18%); la presentación necesita espacio para el panel de estadísticas lateral.
- El pie de página debe dibujarse con coordenadas relativas a la figura (`fig.text()`), no al eje, para que funcione correctamente en cualquier tamaño de salida.
- `axhline` con `transform` no funciona en todos los contextos de matplotlib — `ax.plot()` con `transform=ax.transAxes` es más robusto.
- Mantener las paletas de color en un diccionario centralizado (`PALETAS`) facilita añadir nuevos índices sin modificar el resto del código.
- El ajuste exacto del mapa al shapefile (sin padding) da una apariencia mucho más profesional, especialmente en el formato Instagram.

---

## CHECKLIST FINAL SEMANA 2 ✅

- [x] Script `04_generar_mapa.py` funcional para los 6 índices
- [x] Formato impreso A3 generado (horizontal y vertical)
- [x] Formato Instagram generado (1080×1080, fondo oscuro)
- [x] Formato presentación generado (1920×1080, panel lateral)
- [x] Paleta MNDWI añadida al script
- [x] Pie de página embebido correctamente en los tres formatos
- [x] Escala y norte en color correcto según fondo
- [x] Leyenda reposicionable por parámetro
- [x] Mapas verificados visualmente en QGIS y visor de imágenes
- [x] Archivos guardados en `datos/processed/Podocarprocessed/clasificacion/mapas/`

---

## PRÓXIMO PASO — SEMANA 3

Clasificación supervisada de cobertura vegetal usando el mosaico multibanda y los índices como capas auxiliares:

1. Recolección de puntos de entrenamiento en QGIS (mínimo 50 por clase)
2. Exportar puntos a CSV con valores de bandas e índices (`scripts/extraer_valores.py`)
3. Entrenar clasificador Random Forest (`scripts/02_clasificar_cobertura.py`)
4. Aplicar modelo a todo el mosaico (procesamiento en bloques para memoria)
5. Validar con matriz de confusión (objetivo: accuracy > 85%)
6. Generar mapa de cobertura vegetal Podocarpus 2024

**Clases previstas:** bosque denso, bosque intervenido, pastizal, agua, suelo desnudo.

---

*Ficha actualizada — abril de 2026. Script reutilizable para cualquier área de Ecuador.*
