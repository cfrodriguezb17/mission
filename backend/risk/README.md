# IRPC — fórmula irpc-v1

La fórmula sigue el algoritmo del enunciado. Para inflación de 9,2 %, este resta
10 puntos, aunque el ejemplo original resta 25. Se adopta el algoritmo y se
documentan las ambigüedades para que el cálculo sea reproducible.

## Fórmula

Cada score empieza en 100, resta una sola penalización por variable (el tramo
más severo aplicable) y se acota a cero. Comparaciones estrictas `<` y `>`:

| Score | Variable | Tramos → penalización |
| --- | --- | --- |
| Económico | PIB per cápita USD | <3000 → 30; <6000 → 15; <12000 → 5 |
| Económico | Inflación % | >50 → 40; >10 → 25; >5 → 10 |
| Económico | Desempleo % | >15 → 25; >10 → 15; >7 → 5 |
| Económico | Deuda/PIB % | >80 → 20; >50 → 10 |
| Cambiario | Desviación estándar de variaciones diarias % | >3 → 40; >1,5 → 25; >0,5 → 10 |
| Cambiario | Depreciación acumulada % | >10 → 30; >5 → 15; >2 → 5 |
| Estabilidad | Balanza comercial % PIB | <-10 → 25; <-5 → 15; <0 → 5 |
| Estabilidad | Crecimiento PIB % | <-2 → 30; <0 → 20; <1 → 10 |
| Estabilidad | Indicadores en riesgo | 5 por indicador distinto con penalización |

Compuesto = económico × 0,40 + cambiario × 0,30 + estabilidad × 0,30.
Decimal con precisión intermedia de 64 dígitos y redondeo final ROUND_HALF_UP
a dos decimales; los tramos se evalúan antes de redondear.
Nivel/color: ≥75 BAJO/#22c55e, ≥50 MODERADO/#eab308, ≥25 ALTO/#f97316,
<25 CRITICO/#ef4444.

## Decisiones sobre ambigüedades

- Cada indicador usa su última observación de un año completo (menor que el
  año UTC del cálculo). Se registra el año de cada entrada, que puede diferir.
  Crecimiento usa el PIB más reciente y el del año inmediatamente anterior:
  `(actual-anterior)/anterior × 100`. Si falta alguno o el anterior es ≤0,
  queda ausente; no se salta a un año más antiguo.
- «Indicadores negativos» cuenta una vez cada uno de los cuatro indicadores
  económicos penalizados, la balanza penalizada y el PIB si su crecimiento
  recibe penalización. No significa simplemente valores menores que cero.
- Ventana cambiaria: desde fecha UTC del cálculo menos 30 días hasta esa fecha,
  ambas incluidas. Para 30 variaciones hacen falta 31 cotizaciones. Solo se
  comparan días consecutivos del par moneda local → USD; no se rellenan huecos.
  Desviación estándar poblacional con las variaciones disponibles, con al menos
  dos. Los huecos quedan registrados aunque pueda calcularse volatilidad.
- Depreciación = `max(0, (1-tasa_final/tasa_inicial) × 100)`, porque la tasa
  es USD por unidad local. Requiere ambas fechas exactas; apreciación no penaliza.
  Ecuador/USD usa identidad: score cambiario 100 y `no_aplica=true`.
- Los faltantes no se convierten en cero ni se penalizan. Se exponen en
  `detalle_calculo.missing_indicators` y `datos_parciales`. Sin entradas, el
  índice puede ser 100 con datos parciales: debe interpretarse junto con esa
  evidencia. Los datos simulados se identifican en cada entrada y mediante
  `contiene_simulaciones`. El seed ahora incluye 31 cotizaciones por moneda y
  cubre los 30 días completos sin modificar los valores del seed anterior.

### Ejemplo coherente con irpc-v1

Con PIB per cápita 6.800, inflación 9,2 %, desempleo 11,3 %, deuda/PIB 55 %,
volatilidad 0,8 %, depreciación 1,5 %, balanza -4,2 % y crecimiento PIB 1,5 %:
económico = 100 - 5 - 10 - 15 - 10 = 60; cambiario = 90.
Hay cinco indicadores distintos penalizados (los cuatro económicos y balanza),
por lo que estabilidad = 100 - 5 - 25 = 70. Compuesto = 60×0,40 + 90×0,30 +
70×0,30 = **72,00**, MODERADO. El ejemplo original utiliza otra penalización de
inflación y dice tres indicadores negativos sin definirlos; no es reproducible
con estos criterios. Este ejemplo describe entradas controladas, no datos reales.

## Persistencia y API

IndiceRiesgo guarda los cuatro decimales (5, 2), versión y evidencia JSON de
indicadores/cotizaciones con sus valores, fechas, fuentes, penalizaciones y
faltantes. Checks 0–100 y versión no vacía; índice (pais, fecha_calculo).
Admin de consulta, sin crear, editar ni borrar resultados. Un recálculo crea
otra instantánea incluso el mismo día. Un empate de timestamp se resuelve por
id más reciente. Ediciones posteriores de economics no alteran la evidencia.

Todos los endpoints requieren JWT; ADMIN, ANALISTA y VIEWER pueden consultar.
Solo el rol ADMIN puede recalcular, incluso para superusuarios Django.

| Método | Endpoint | Comportamiento |
| --- | --- | --- |
| GET | `/api/riesgo/` | Último cálculo por país activo, compuesto descendente y país. Países sin cálculo no aparecen. |
| GET | `/api/riesgo/{codigo_iso}/` | `ultimo` sin filtros y `historico` paginado. Sin cálculos: ultimo=null e histórico vacío. |
| GET | `/api/riesgo/{codigo_iso}/historico/` | Histórico paginado; `fecha_inicio`/`fecha_fin` inclusivos en UTC. |
| POST | `/api/riesgo/calcular/` | `{}` para todos los países activos o `{"paises":["CO","EC"]}`; devuelve `calculados` y `errores`. |

Listados admiten page, page_size (20 por defecto, máximo 100) y ordering:
pais, fecha_calculo, indice_compuesto, score_economico, score_cambiario,
score_estabilidad e id, con `-` descendente. Histórico y detalle admiten rango
de fechas. Parámetros inválidos: 400; país desconocido/inactivo: 404;
sin JWT: 401; sin rol ADMIN para recalcular: 403. Si todo recálculo falla: 503;
fallos parciales: 200 con errores explícitos.

## Coordinación y ejecución

`backend.workflows` coordina el endpoint de sincronización y los comandos
sync_indicadores/update_tipos_cambio: persisten datos económicos y recalculan
únicamente los países procesados. La respuesta añade `riesgos`,
`recalculo_pendiente` y `alertas_pendientes`: el módulo alerts ya está implementado
y se ejecuta después del recálculo, incluido el endpoint/comando administrativo.
Los indicadores de pendiente quedan true ante errores o trabajos de alertas
todavía sin procesar en el alcance.
Los servicios básicos de economics siguen aislados de risk.
HTTP opera fuera de transacciones; cada cálculo bloquea país y moneda para
conservar una instantánea coherente con las escrituras de economics.
Los comandos fallan ante errores de sincronización o recálculo.

Cada índice nuevo conserva `fecha_alertas_procesadas=NULL` dentro de la
transacción del cálculo. Alerts confirma el marcador y sus eventos juntos,
también cuando ninguna regla aplica. El recuperador consulta todos los índices
pendientes del alcance, incluidos históricos. `risk.0002_indice_alertas_procesadas`
revisa únicamente el último índice previo por país; los anteriores se excluyen
de revisión retrospectiva para evitar notificaciones masivas. El marcador es
interno y no se expone en el serializador del índice.
[Límites, política de migración y contrato de pendientes](../alerts/README.md).

```bash
python manage.py migrate
python manage.py calcular_riesgos
python manage.py calcular_riesgos --paises CO EC
python manage.py test risk --noinput
python manage.py verify_migrations
python manage.py verify_migrations --fresh
```

Las pruebas cubren tramos/umbrales, compuesto 69 con entradas controladas,
faltantes, huecos cambiarios, precisión extrema, USD, evidencia histórica,
roles, paginación, orden, coordinación, fallos parciales, concurrencia y HTTP/JWT.
El test de compuesto no reconstruye entradas de Colombia ausentes de la
transcripción; prueba la fórmula y el criterio de indicadores documentado.
