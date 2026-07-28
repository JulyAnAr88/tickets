# Documentación del Sistema de Reintegros — Pase a Producción

## 1. Resumen de cambios

Se implementó la lógica de evaluación automática de reintegros para tickets de viáticos,
basada en condiciones configuradas por protocolo. El sistema analiza cada ticket contra
las reglas definidas y genera sugerencias de tipo:

| Sugerencia | Significado |
|---|---|
| `VIÁTICOS INCLUIDOS` | El protocolo cubre este concepto — no se factura |
| `REFACTURAR` | El exceso sobre la base debe refacturarse al sponsor |
| `REQUIERE APROBACION` | El exceso total desde la base supera el umbral de aprobación — requiere autorización |

---

## 2. Lógica de evaluación (regla de negocio)

Para cada ticket se identifica el protocolo (por similitud de nombre) y se obtienen
sus reglas de reintegro. Cada regla tiene:

- **Concepto**: qué concepto evalúa (viático base, desayuno, comida, traslado, etc.)
- **Condición**: cuándo se aplica (siempre, si supera un monto, si supera una distancia, etc.)
- **Monto**: cómo se calcula el valor (fijo, reembolso por diferencia, por kilómetro, etc.)
- **Requisito**: documentación necesaria

### 2.1 Flujo de evaluación

```
Para cada regla del protocolo:
  1. Filtros de categoría:
     - Si es DESAYUNO/COMIDA/HOTEL y el ticket es de traslado → se salta
     - Si es TRASLADO/KILOMETRAJE y el ticket NO es de traslado → se salta

  2. Evaluación de condición:
     - SIEMPRE → aplica siempre
     - SUPERA_MONTO → aplica si gasto_usd > umbral
     - RANGO_MONTO → aplica si gasto está entre umbral_min y umbral_max
     - DISTANCIA_SUPERA → aplica si distancia > umbral

  3. Determinación de sugerencia y monto:
```

### 2.2 Regla específica para REEMBOLSO vs APROBACIÓN

Cuando un protocolo tiene dos reglas de tipo SUPERA_MONTO:
- **REEMBOLSO_DIFERENCIA** (ej: gasto > 100 USD)
- **APROBACION_ESPECIAL** (ej: gasto > 150 USD)

La lógica es:

| Escenario | Resultado |
|---|---|
| `gasto ≤ umbral_base` (ej: ≤ 100 USD) | Solo VIÁTICOS INCLUIDOS |
| `umbral_base < gasto ≤ umbral_aprobacion` (ej: 100-150 USD) | **REFACTURAR** = `gasto - umbral_base` (con tope en `monto_valor - umbral_base`) |
| `gasto > umbral_aprobacion` (ej: > 150 USD) | **REQUIERE APROBACION** = `gasto - umbral_base` (sin tope). La regla REEMBOLSO se suprime. |

**Ejemplo concreto** — Protocolo GZP2, base = 100 USD, aprobación = 150 USD:

```
Ticket $236.907 (TC=1520 → 155,86 USD):
  - 155,86 > 150 → REQUIERE APROBACION
  - Monto = (155,86 - 100) × 1520 = $84.907

Ticket $160.480 (TC=1520 → 105,58 USD):
  - 100 < 105,58 ≤ 150 → REFACTURAR (capped)
  - Monto = min(105,58 - 100, 150 - 100) × 1520 = 5,58 × 1520 = $8.480
```

### 2.3 Consumo del pool

El sistema mantiene un "pool" del importe total del ticket. Cada regla que aplica
consume del pool:

- `VIÁTICOS INCLUIDOS` (tipo FIJO): consume el monto fijo del pool
- `REFACTURAR`: consume el monto sugerido del pool (acotado al pool restante)
- `REQUIERE APROBACION`: **NO** consume del pool (es informativo/de autorización)

Esto asegura que la suma de lo incluido más lo refacturado no supere el importe
total del ticket.

### 2.4 Protocolos sin reglas de base (EZEF, GZBO)

Para EZEF y GZBO, los traslados son cubiertos por el sponsor (Greenphire/Lilly).
Cuando el centro paga un traslado por contingencia:
- `es_traslado=true` → **REFACTURAR** por el **monto completo** del ticket
- `es_traslado=false` → solo aplica desayuno como VIÁTICOS INCLUIDOS

---

## 3. Cambios en la base de datos

### 3.1 Esquema `auxiliar`

Se copiaron y modificaron tablas en el esquema `auxiliar` (entorno de pruebas).
Para producción, los mismos cambios deben aplicarse al esquema `cedir`.

#### Tablas copiadas desde `cedir` a `auxiliar`

| Tabla | Propósito |
|---|---|
| `ticket` | Tickets de viáticos (553 registros copiados) |
| `ticket_procesado` | Resultados de evaluación de reintegros |
| `protocolo` | Protocolos de estudio |
| `reintegro` | Reglas de reintegro |
| `concepto_reintegro` | Conceptos (desayuno, viático base, etc.) |
| `condicion_reintegro` | Condiciones de aplicación |
| `tipo_condicion` | Tipos de condición (SIEMPRE, SUPERA_MONTO, etc.) |
| `monto_reintegro` | Configuración de montos |
| `requisito_reintegro` | Requisitos documentales |
| `protocolo_reintegro` | Asignación de reglas a protocolos |

#### Tablas nuevas en `auxiliar` (creadas, no copiadas)

Ninguna — todas fueron copiadas desde `cedir` con la misma estructura.

### 3.2 Correcciones aplicadas

#### a) Protocolo_reintegro duplicados

Se eliminaron filas duplicadas en `auxiliar.protocolo_reintegro` (EZEF y GZBO
tenían el mismo `id_reintegro=31` asignado dos veces).

```sql
DELETE FROM auxiliar.protocolo_reintegro
WHERE ctid NOT IN (
    SELECT MIN(ctid) FROM auxiliar.protocolo_reintegro GROUP BY id_protocolo, id_reintegro
);
ALTER TABLE auxiliar.protocolo_reintegro ADD CONSTRAINT uq_protocolo_reintegro
    UNIQUE (id_protocolo, id_reintegro);
```

#### b) Nuevos conceptos y reglas para EZEF/GZBO

Se creó el concepto "Reembolso de traslado (contingencia)" (categoría TRASLADO)
y el monto REEMBOLSO_DIFERENCIA sin tope (`valor_numerico = NULL`), para que
los traslados por contingencia se refacturen por el monto completo.

#### c) Reglas corregidas para GZP1/GZP2

- `parametro_evaluacion` de REEMBOLSO_DIFERENCIA corregido de 150 a 100
- `parametro_evaluacion` de APROBACION_ESPECIAL corregido de 200 a 150
- Monto REEMBOLSO_DIFERENCIA creado con valor = 150 (separado del que usan GZPW/MALO que es 200)

#### d) GZPW - LILLY sin reglas

Se copiaron las reglas desde el protocolo `GZPW` (id=22) a `GZPW - LILLY` (id=33)
para que los tickets que usan el nombre completo tengan reglas asignadas.

### 3.3 Funciones PL/pgSQL modificadas

#### `auxiliar.evaluar_reintegros_por_ticket_trigger`

Función principal que evalúa un ticket contra las reglas del protocolo y
devuelve las sugerencias. Reescrita completamente con la nueva lógica:

Parámetros:
- `p_id_ticket INTEGER` — ID del ticket
- `p_tipo_cambio NUMERIC` — cotización USD (opcional, si es NULL se obtiene de API)
- `p_debug BOOLEAN DEFAULT FALSE` — modo debug con NOTICE

Retorna: `TABLE` con columnas `id_ticket, fecha_viaje, fecha_ticket,
paciente_asociado, tipo_doc, nro_doc, protocolo, importe_total, concepto,
monto_sugerido, sugerencia, tipo_cambio_usado, usuario, se_aplica`

Diferencias con la versión original de `cedir`:

| Aspecto | Versión original (`cedir`) | Nueva versión (`auxiliar`) |
|---|---|---|
| Sugerencia APROBACION | `'APROBACION'` | `'REQUIERE APROBACION'` |
| Supresión REEMBOLSO | No existía | Se suprime cuando gasto > umbral de aprobación |
| Cálculo APROBACION | `gasto - umbral_aprobacion` | `gasto - umbral_base` (exceso total desde la base) |
| Búsqueda de reglas | Solo en `cedir` | Primero en `auxiliar`, fallback a `cedir` |

#### `auxiliar.procesar_ticket_trigger`

Trigger function que se dispara AFTER INSERT OR UPDATE en `auxiliar.ticket`.
Inserta los resultados de `evaluar_reintegros_por_ticket_trigger` en
`auxiliar.ticket_procesado`.

Se corrigió el llamado a la función evaluadora para pasar los parámetros
en el orden correcto.

---

## 4. Configuración de reglas por protocolo

### 4.1 Reglas existentes (configuradas en `auxiliar`)

| Protocolo | Reglas | Base | Aprobación |
|---|---|---|---|
| GZP1 - LILLY | Base, REEMBOLSO (cap 150), APROBACION (>150), Desayuno, Comida | 100 USD | 150 USD |
| GZP2 - LILLY | Base, REEMBOLSO (cap 150), APROBACION (>150), Desayuno, Comida | 100 USD | 150 USD |
| GZPW | Base, REEMBOLSO (cap 200), APROBACION (>200), Desayuno, Comida | 150 USD | 200 USD |
| MALO - LILLY | Base, REEMBOLSO (cap 200), APROBACION (>200), Desayuno, Comida | 150 USD | 200 USD |
| EKBG - LILLY | Base, REEMBOLSO (cap 150), APROBACION (>150), Desayuno | 100 USD | 150 USD |
| GPJA - LILLY | Base, REEMBOLSO (cap 150), APROBACION (>150), Desayuno, Comida, Km | 100 USD | 150 USD |
| GPIJ - LILLY | Base, REEMBOLSO×2 (cap 100/200), APROBACION (>100), Desayuno, Km | 50 USD | 100 USD |
| EZEF - LILLY | Desayuno, Traslado-contingencia | — | — |
| GZBO - LILLY | Desayuno, Traslado-contingencia | — | — |

### 4.2 Reglas faltantes (según ODS)

| Protocolo | Faltante |
|---|---|
| GZPW, MALO | Hotel ($300/noche), Comida cuidador ($25) |
| EKBG | Comidas (>145km, $25), Hotel ($300/noche) |
| GPJA | Comida cuidador (hasta 4), Hotel ($300/noche) |
| GPIJ | Peajes/estacionamiento, Hotel ($231/noche), Comidas paciente ($19) |
| EZEF | Comidas (>145km, $19), Hotel (Lilly), Reembolso excepcional, Hotel contingencia ($231) |
| GZBO | Comidas paciente ($19), Preselección ($66), Comidas (>145km, $19), Hotel (Lilly), Hotel contingencia ($231) |
| GZPO | **Protocolo no existe** — crear + 6 reglas |

---

## 5. Nuevo endpoint web: ABM Criterios de Reintegro

Se agregó una interfaz web para gestionar las reglas de reintegro sin necesidad
de SQL directo.

### Rutas

| Ruta | Método | Descripción |
|---|---|---|
| `/abm/reintegros` | GET | Página principal con selector de protocolo y tabla de reglas |
| `/abm/reintegros/api/listar/<id>` | GET | JSON con las reglas de un protocolo |
| `/abm/reintegros/api/agregar` | POST | Crea un nuevo reintegro + lo asigna al protocolo |
| `/abm/reintegros/api/editar/<id>` | POST | Modifica un reintegro existente |
| `/abm/reintegros/api/eliminar` | POST | Elimina la asignación y el reintegro |

### Archivos

- `templates/criterios_reintegro.html` — Interfaz ABM
- `static/js/criterios_reintegro.js` — Lógica AJAX
- Sidebar: nuevo enlace "Criterios de Reintegro"

---

## 6. Pendiente para el pase a producción

### 6.1 Aplicar funciones en esquema `cedir`

```sql
-- Reemplazar la función en cedir con la nueva lógica
CREATE OR REPLACE FUNCTION cedir.evaluar_reintegros_por_ticket_trigger(...)
```

**Importante**: la función en `cedir` tiene una firma distinta a `auxiliar`
(los nombres de columnas retornadas son diferentes). Se debe reemplazar
completamente.

### 6.2 Completar reglas faltantes

Ver sección 4.2 — hay 7 protocolos con reglas incompletas y 1 protocolo
(GZPO) que no existe en la base.

### 6.3 Verificar trigger de ticket

El trigger `trg_procesar_ticket` debe estar activo en `cedir.ticket` para
que al insertar o actualizar un ticket, se evalúen automáticamente los
reintegros.

### 6.4 Ajustar tipo de cambio histórico

Actualmente `obtener_tipo_cambio_api()` devuelve la cotización del día actual.
Para tickets de fechas anteriores, el monto sugerido puede diferir del esperado.
Evaluar si es necesario usar la cotización histórica de la fecha del ticket.

---

## 7. Pruebas de validación

Para verificar el correcto funcionamiento después del pase a producción,
probar los siguientes casos:

```sql
-- Ticket entre base y aprobación → debe dar REFACTURAR
SELECT * FROM cedir.evaluar_reintegros_por_ticket_trigger(
    (SELECT id FROM cedir.ticket WHERE protocolo ILIKE '%GZP2%' 
     AND importe_total / cedir.obtener_tipo_cambio_api() BETWEEN 100 AND 150 LIMIT 1)
);

-- Ticket sobre aprobación → debe dar REQUIERE APROBACION (sin REFACTURAR)
SELECT * FROM cedir.evaluar_reintegros_por_ticket_trigger(
    (SELECT id FROM cedir.ticket WHERE protocolo ILIKE '%GZP2%' 
     AND importe_total / cedir.obtener_tipo_cambio_api() > 150 LIMIT 1)
);

-- Ticket GZBO/EZEF con traslado → debe dar REFACTURAR por monto completo
SELECT * FROM cedir.evaluar_reintegros_por_ticket_trigger(
    (SELECT id FROM cedir.ticket WHERE protocolo ILIKE '%GZBO%' AND es_traslado = true LIMIT 1)
);
```

---

## 8. Historial de cambios en archivos

| Archivo | Cambio |
|---|---|
| `app.py` | +6 rutas para CRUD de reintegros, + función `get_schema()` |
| `templates/criterios_reintegro.html` | Nuevo — ABM de reglas de reintegro |
| `templates/sidebar_desktop.html` | + link "Criterios de Reintegro" |
| `templates/sidebar_mobile.html` | + link "Criterios de Reintegro" |
| `static/js/criterios_reintegro.js` | Nuevo — lógica AJAX para el ABM |
| `docs/REINTEGROS.md` | Este documento |

### Base de datos (esquema `auxiliar`)

| Objeto | Cambio |
|---|---|
| `auxiliar.evaluar_reintegros_por_ticket_trigger` | Reescrita — nueva lógica de REQUIERE APROBACION + supresión condicional de REFACTURAR |
| `auxiliar.procesar_ticket_trigger` | Corregido — parámetros de llamada, nombres de columnas, cast de nro_doc |
| `auxiliar.protocolo_reintegro` | + UNIQUE(id_protocolo, id_reintegro), duplicados eliminados |
| `auxiliar.concepto_reintegro` | + "Reembolso de traslado (contingencia)" (cat=TRASLADO) |
| `auxiliar.monto_reintegro` | + REEMBOLSO_DIFERENCIA sin tope (valor_numerico=NULL) |
| `auxiliar.condicion_reintegro` | + "Traslado abonado por el centro" (SUPERA_MONTO, param=0) |
| `auxiliar.reintegro` | + regla de traslado contingencia (id=31) |
| `auxiliar.protocolo_reintegro` | Nuevas asignaciones: EZEF→31, GZBO→31; GZPW - LILLY→reglas copiadas desde GZPW |
