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
| TC cuando es NULL | `obtener_tipo_cambio_api()` (hoy) | `obtener_tipo_cambio(fecha_ticket)` (por fecha del ticket) |
| Sin protocolo | Evalúa todas las reglas | **No evalúa nada** (0 filas hasta que el protocolo se asocie) |

#### `auxiliar.procesar_ticket_trigger`

Trigger function que se dispara AFTER INSERT OR UPDATE en `auxiliar.ticket`.
Inserta los resultados de `evaluar_reintegros_por_ticket_trigger` en
`auxiliar.ticket_procesado`.

El llamado a la función evaluadora pasa `p_tipo_cambio = NULL`, por lo que
la cotización se obtiene **por la fecha del ticket** (`fecha_ticket`, con
fallback a `fecha_viaje` → `create_time` → día actual) a través de
`auxiliar.obtener_tipo_cambio()`.

Si el ticket no matchea ningún protocolo, la función no devuelve filas y
no se inserta nada en `ticket_procesado` (se espera a que el protocolo
esté correctamente configurado).

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

## 5. Especificación de API para ABM de Reglas de Reintegro

Esta sección describe los endpoints REST necesarios para implementar un ABM
de reglas de reintegro en otra aplicación. Cada regla de reintegro es una
combinación de 4 componentes (concepto, condición, monto, requisito) asignada
a un protocolo.

### 5.1 Esquema de la base de datos (modelo relacional)

```
protocolo ──┬── protocolo_reintegro ──┬── reintegro ──┬── concepto_reintegro
            │                         │               ├── condicion_reintegro
            │                         │               ├── monto_reintegro
            │                         │               └── requisito_reintegro
```

#### `protocolo`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | ID del protocolo |
| `identificador_protocolo` | VARCHAR(50) | Nombre del protocolo (ej: "GZP1 - LILLY") |

#### `reintegro` — regla individual

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | ID de la regla |
| `id_concepto` | SMALLINT FK → `concepto_reintegro.id` | Concepto que evalúa |
| `id_condicion` | INTEGER FK → `condicion_reintegro.id` | Condición de aplicación |
| `id_monto` | INTEGER FK → `monto_reintegro.id` | Cálculo del monto |
| `id_requisito` | INTEGER FK → `requisito_reintegro.id` | Documentación requerida (nullable) |

#### `protocolo_reintegro` — asignación N:M

| Columna | Tipo | Descripción |
|---|---|---|
| `id_protocolo` | SMALLINT FK → `protocolo.id` | Protocolo |
| `id_reintegro` | SMALLINT FK → `reintegro.id` | Regla asignada |
| UNIQUE(`id_protocolo`, `id_reintegro`) | | |

#### `concepto_reintegro`

| Columna | Tipo | Valores ejemplo |
|---|---|---|
| `id` | INTEGER PK | |
| `descripcion` | VARCHAR(150) | "Viático base", "Desayuno", "Comida" |
| `categoria` | VARCHAR(30) | `VIATICO_BASE`, `DESAYUNO`, `COMIDA`, `HOTEL`, `TRASLADO`, `KILOMETRAJE`, `OTRO` |

#### `condicion_reintegro`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | |
| `descripcion` | VARCHAR(150) | Texto legible |
| `id_tipo_condicion` | INTEGER FK → `tipo_condicion.id` | Tipo de condición |
| `parametro_evaluacion` | NUMERIC(10,2) | Umbral (nullable según tipo) |

#### `tipo_condicion`

| Columna | Tipo | Valores ejemplo |
|---|---|---|
| `id` | INTEGER PK | |
| `codigo` | VARCHAR(50) | `SIEMPRE`, `SUPERA_MONTO`, `RANGO_MONTO` |

#### `monto_reintegro`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | |
| `tipo` | VARCHAR(50) | `FIJO`, `REEMBOLSO_DIFERENCIA`, `POR_KILOMETRO` |
| `valor_numerico` | NUMERIC(10,2) | Valor fijo o tope máximo (nullable si sin tope) |
| `unidad` | VARCHAR(50) | `USD`, `km` (nullable) |
| `texto_extra` | VARCHAR(200) | Texto adicional (nullable) |

#### `requisito_reintegro`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | |
| `descripcion` | VARCHAR(150) | Ej: "Ticket original + orden de viaje" |

### 5.2 Endpoints requeridos

#### Listar reglas de un protocolo

```
GET /api/reintegros?protocolo_id=<id>
```

Respuesta:
```json
{
  "reglas": [
    {
      "id_protocolo": 2,
      "id_reintegro": 1,
      "id_concepto": 1,
      "concepto": "Viático base",
      "categoria": "VIATICO_BASE",
      "id_condicion": 1,
      "condicion": "Siempre aplica",
      "tipo_codigo": "SIEMPRE",
      "parametro_evaluacion": null,
      "id_monto": 1,
      "monto_tipo": "FIJO",
      "monto_valor": 100.00,
      "monto_unidad": "USD",
      "id_requisito": 1,
      "requisito": "Ticket original"
    }
  ]
}
```

#### Crear regla y asignarla a un protocolo

```
POST /api/reintegros
Content-Type: application/json

{
  "id_protocolo": 2,
  "id_concepto": 1,
  "id_condicion": 2,
  "id_monto": 3,
  "id_requisito": null
}
```

Acción en un solo paso:
1. INSERT en `reintegro` con los IDs dados → obtener `new_id`
2. INSERT en `protocolo_reintegro` (`id_protocolo`, `id_reintegro` = `new_id`)

Respuesta:
```json
{
  "success": true,
  "id_reintegro": 32
}
```

Campos obligatorios: `id_protocolo`, `id_concepto`, `id_condicion`, `id_monto`.

Si `id_requisito` es null, se guarda como NULL.

#### Editar una regla existente

```
PUT /api/reintegros/:id
Content-Type: application/json

{
  "id_concepto": 2,
  "id_condicion": 3,
  "id_monto": 4,
  "id_requisito": null
}
```

UPDATE directo sobre `reintegro` donde `id = :id`.

Respuesta: `{"success": true}`

#### Eliminar regla y su asignación

```
DELETE /api/reintegros/:protocolo_id/:reintegro_id
```

Dos pasos en una transacción:
1. DELETE de `protocolo_reintegro` WHERE `id_protocolo = :protocolo_id AND id_reintegro = :reintegro_id`
2. DELETE de `reintegro` WHERE `id = :reintegro_id`

Respuesta: `{"success": true}`

#### Listar todos los protocolos (para selector)

```
GET /api/protocolos
```

```json
{
  "protocolos": [
    {"id": 2, "identificador_protocolo": "GZP2 - LILLY"},
    ...
  ]
}
```

#### Listar catálogos (conceptos, condiciones, montos, requisitos)

```
GET /api/catalogos/reintegros
```

```json
{
  "conceptos": [{"id": 1, "descripcion": "Viático base", "categoria": "VIATICO_BASE"}, ...],
  "condiciones": [{"id": 1, "descripcion": "Siempre aplica", "tipo_codigo": "SIEMPRE", "parametro_evaluacion": null}, ...],
  "montos": [{"id": 1, "tipo": "FIJO", "valor_numerico": 100.00, "unidad": "USD", "texto_extra": null}, ...],
  "requisitos": [{"id": 1, "descripcion": "Ticket original"}, ...]
}
```

### 5.3 Reglas de negocio a respetar en el frontend

1. Una regla de tipo `APROBACION_ESPECIAL` solo tiene sentido si existe una
   regla `REEMBOLSO_DIFERENCIA` en el mismo protocolo con un umbral menor.
2. `VIÁTICOS INCLUIDOS` (FIJO) y `REEMBOLSO_DIFERENCIA` (con o sin tope)
   son los únicos tipos que consumen del "pool" del ticket. `APROBACION_ESPECIAL`
   es informativo.
3. Las categorías DESAYUNO/COMIDA/HOTEL se excluyen automáticamente si el
   ticket es de traslado. Las categorías TRASLADO/KILOMETRAJE se excluyen
   si el ticket NO es de traslado. Ver sección 2.1.

### 5.4 Consideraciones de implementación

- Todas las tablas referidas están en un mismo esquema (ej: `cedir` o `auxiliar`).
- Usar transacciones para las operaciones de crear y eliminar (2 INSERT o 2 DELETE).
- El catálogo `condicion_reintegro` requiere JOIN con `tipo_condicion` para
  obtener el `codigo` (SIEMPRE, SUPERA_MONTO, etc.).
- Los valores `parametro_evaluacion` y `monto_valor` se almacenan en la moneda
  configurada en `monto_reintegro.unidad` (generalmente USD).
- La evaluación de cada regla la hace la función PL/pgSQL
  `evaluar_reintegros_por_ticket_trigger()` — el ABM solo gestiona la
  configuración, no ejecuta la evaluación.

---

## 5.5 Tipo de cambio histórico

### 5.5.1 Tabla `auxiliar.cotizacion_historica`

Almacena cotizaciones USD por fecha para usarlas en la evaluación de tickets
de fechas anteriores sin depender de la cotización del día actual.

```sql
CREATE TABLE auxiliar.cotizacion_historica (
    fecha DATE PRIMARY KEY,
    cotizacion NUMERIC(10,2) NOT NULL,
    fuente VARCHAR(50) DEFAULT 'API',
    actualizado TIMESTAMP DEFAULT NOW()
);
```

### 5.5.2 Función `auxiliar.obtener_tipo_cambio(p_fecha DATE)`

Reemplaza a `cedir.obtener_tipo_cambio_api()` para obtener la cotización
correspondiente a la fecha del ticket. Estrategia de búsqueda:

1. Busca en `cotizacion_historica` la fecha exacta
2. Si no la encuentra, busca hasta 7 días hacia atrás
3. Si no hay dato histórico, intenta obtenerla de la API de dolarapi.com
   para la fecha específica (`GET /v1/dolares/oficial/YYYY-MM-DD`)
4. Si la API no devuelve dato, usa la cotización del día actual como fallback

Los valores obtenidos de la API se almacenan automáticamente en
`cotizacion_historica` para reutilización futura.

### 5.5.3 Integración en la evaluación

La función `evaluar_reintegros_por_ticket_trigger` ahora determina el TC
así:

```sql
v_tc_fecha := COALESCE(
    v_ticket.fecha_ticket,     -- 1ra opción
    v_ticket.fecha_viaje,      -- 2da opción
    v_ticket.create_time::DATE, -- 3ra opción
    CURRENT_DATE               -- fallback
);
v_tipo_cambio_efectivo := auxiliar.obtener_tipo_cambio(v_tc_fecha);
```

Si se pasa `p_tipo_cambio` explícitamente, se usa ese valor directamente
(sin búsqueda por fecha).

---

## 6. Pase a producción (COMPLETADO el 31/07/2026)

### 6.1 Funciones y catálogos aplicados en esquema `cedir`

Se migró toda la lógica corregida desde `auxiliar` a `cedir`:

- `cedir.evaluar_reintegros_por_ticket_trigger` reemplazada con la nueva
  lógica (REQUIERE APROBACION + supresión condicional de REFACTURAR, TC por
  fecha del ticket, 0 filas sin protocolo). Firma mantenida para compatibilidad
  con el trigger: `(p_id_ticket integer, p_debug boolean DEFAULT false,
  p_tipo_cambio numeric DEFAULT NULL)` retornando `nro_doc integer` y
  `cotizacion numeric`.
- En vez de `c.categoria` (inexistente en cedir), se hace JOIN a
  `cedir.tipo_concepto_reintegro` para obtener la categoría
  (`tcr.nombre`).
- **Fix pool**: el descuento FIJO del pool solo ocurre cuando `v_aplica = TRUE`
  (antes se descontaba sin verificar `v_aplica`, dando monto 0 en tickets
  GZP1/GZP2 con gastos de 100–150 USD).
- Catálogos reemplazados por los de `auxiliar` (consolidados):
  `concepto_reintegro` (14), `condicion_reintegro` (7, se descartó el duplicado
  auxiliar id=7), `monto_reintegro` (26, incluye TOPE 25 y FIJO 80 nuevos),
  `requisito_reintegro` (16), `reintegro` (24), `protocolo_reintegro` (55).
- Sin referencias rotas y sin combos duplicados en `reintegro`
  (se conserva `uk_reintegro_unique`).
- Duplicados de `auxiliar.reintegro` (28/30) eliminados también en auxiliar;
  protocolos 1/2 y 5/7 apuntan a la reintegro consolidada (8).

### 6.2 Tipo de cambio histórico en cedir

- Tabla `cedir.cotizacion_historica` creada y sembrada desde `auxiliar`
  (2026-03-06=1407, 2026-03-13=1410, 2026-07-28=1520, 2026-07-31=1510).
- `cedir.obtener_tipo_cambio(p_fecha)` y
  `cedir.obtener_cotizacion_api_por_fecha(p_fecha)` replicadas desde auxiliar,
  con fallback a `cedir.obtener_tipo_cambio_api()`.

### 6.3 Reproceso de tickets con TC histórico (31/07/2026)

- Sembrado completo de `cedir.cotizacion_historica` para las **186 fechas**
  de tickets existentes:
  - 160 fechas con `venta` oficial real de la API
    `api.argentinadatos.com/v1/cotizaciones/dolares/oficial` (fuente `API`),
    sobrescribiendo las semillas manuales de marzo (2026-03-06→1435,
    2026-03-13→1420, antes 1407/1410).
  - 26 fechas sin histórico (12 legado 2000/2008 + 14 futuras) sembradas con
    la cotización vigente de `ticket_procesado` o el TC de hoy (1510) con
    fuente `BACKUP`, para evitar TC=1 por fallback.
- Backup de seguridad previo al reproceso en esquema `backup_20260731`
  (tablas `ticket` con 567 filas y `ticket_procesado` con 889 filas).
- Reproceso ejecutado con `UPDATE cedir.ticket SET protocolo = protocolo`
  (dispara `trg_procesar_ticket` por fila). Resultado:

| Métrica | Antes | Después |
|---|---|---|
| Filas activas en `ticket_procesado` | 536 | 667 |
| Tickets con filas activas | 342 | 429 |
| Tickets sin filas activas | 225 | 138 |

- Efectos esperados:
  - Ticket 566 (protocolo NULL) perdió sus 7 filas activas (0 filas hasta
    que se le asocie protocolo).
  - Los montos existentes se recomputaron con TC histórico real
    (ej: ticket 172 GZP2 pasó de TC 1407 a 1435 → REQUIERE APROBACION $93.404,15).
- Verificado: la salida del trigger coincide fila a fila con la llamada
  directa a `cedir.evaluar_reintegros_por_ticket_trigger(172)`.

### 6.4 Fix de la API de cotización histórica (31/07/2026)

- La API original `dolarapi.com/v1/dolares/oficial/YYYY-MM-DD` devuelve
  **vacío** para fechas pasadas, por lo que el fallback caía siempre al TC
  del día.
- `cedir.obtener_cotizacion_api_por_fecha(p_fecha)` reescrita para consultar
  `https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial`, que
  devuelve el histórico completo de la casa `oficial` desde 2011.
- **Fix clave del parseo**: el filtro `sed` cambió de `/^{/,$ p` a
  `/^[\[{]/,$ p` porque argentinadatos devuelve un **array** que comienza
  con `[` (dolarapi devuelve un objeto `{`).
- El valor se extrae con `jsonb_array_elements` filtrando `fecha = p_fecha`.
- Cobertura: argentinadatos cubre 2011→2026-07-30. Fuera de ese rango la
  función devuelve NULL y el fallback sigue siendo
  `cedir.obtener_tipo_cambio_api()` (dolarapi-hoy). Verificado:
  2015-06-01→9, 2012-01-05→4, 2026-07-29→1515; 2000/2028→NULL.

### 6.5 importe_ticket con decimales (01/08/2026)

- La firma de `cedir.evaluar_reintegros_por_ticket_trigger` declaraba
  `importe_ticket integer` y el `RETURN QUERY` casteaba
  `v_importe_total::INTEGER`, truncando los decimales del importe.
- Se hizo `DROP FUNCTION ... CASCADE` (arrastra trigger function y trigger)
  y se recreó con `importe_ticket numeric` y sin el cast. Se recrearon
  `cedir.procesar_ticket_trigger()` y el trigger `trg_procesar_ticket`
  (sin cambios de lógica).
- Reproceso de los 567 tickets (`UPDATE cedir.ticket SET protocolo = protocolo`)
  para regenerar `ticket_procesado` con decimales.
- Resultado: 667 filas activas en 429 tickets (igual que antes), 48 filas
  activas con decimales en `importe_ticket` (ej: ticket 17 → 158017.11).
- Backup del estado previo: `backup_20260731.ticket_procesado_decimales_pre`.

### 6.6 Re-mapeo de protocolos 12/15/41

| Protocolo | Regla | Antes (cedir) | Ahora (cedir) |
|---|---|---|---|
| 12 EFC-18241 SANOFI | Viáticos base | monto 33 (FIJO 100) | reintegro 2 |
| 12 EFC-18241 SANOFI | Reembolso > USD 100 | monto 34 (sin tope) | reintegro 32 |
| 15 BI-1378 | Viáticos base | monto 44 (FIJO 150) | reintegro 1 |
| 15 BI-1378 | Aprobación > USD 200 | monto 7 | reintegro 7 |
| 15 BI-1378 | Desayuno | monto 46 (FIJO 25) | reintegro 10 |
| 15 BI-1378 | Reembolso > USD 150 | monto 34 (sin tope) | reintegro 33 |
| 15 BI-1378 | Comidas cuidador > 145 km | monto 45 (TOPE 25) | reintegro 34 |
| 15 BI-1378 | Comidas paciente > 145 km | monto 45 (TOPE 25) | reintegro 35 |
| 15 BI-1378 | Hotel > 145 km | monto 43 (TOPE 300) | reintegro 36 |
| 41 NN 9490-8024 AMAZE 2 | Viáticos base | monto 47 (FIJO 80) | reintegro 37 |

### 6.7 Trigger verificado

El trigger `trg_procesar_ticket` en `cedir.ticket` sigue activo y la
evaluación automática se comprobó con insert de prueba (rollback): inserta
las filas con `aplica = true` en `cedir.ticket_procesado`.

### 6.8 es_desayuno (01/08/2026)

La regla "SIEMPRE - Desayuno / colación" (FIJO 25 USD) se aplicaba a **todos**
los tickets no traslado, consumiendo del pool. Un ticket con importe menor a
la base + desayuno (125 USD) quedaba con `monto_sugerido = 0` (ej: ticket 17).

Cambios aplicados:

- **Columna nueva**: `cedir.ticket.es_desayuno BOOLEAN DEFAULT FALSE` (también
  en `auxiliar.ticket` por el fallback del evaluador). Los tickets creados
  desde n8n y el insert del sistema llegan con `false` por defecto.
- **Regla de negocio**: en `cedir.evaluar_reintegros_por_ticket_trigger` se
  agregó el filtro `categoria = 'DESAYUNO' AND NOT COALESCE(es_desayuno,FALSE)
  → CONTINUE`. La regla de desayuno solo aplica cuando el ticket está marcado.
- **Frontend**: checkbox "Es desayuno" en `nuevo_ticket.html`, `editar.html`
  y `formulario.html` (solo marcado manual; no hay detección por OCR).
- **Backend**: columna en `models.py`, `TicketForm` en `forms.py`, payload en
  `nuevo_ticket()`, set en `editar()` y `formulario()`, y `es_desayuno` en
  `generate_insert_sql()` / `_normalize_ticket_data()` / `_get_empty_ticket()`.
- Reproceso de los 567 tickets (`UPDATE cedir.ticket SET protocolo = protocolo`).
- Resultado: **448** filas activas en **410** tickets; **0** filas de desayuno
  (ningún ticket está marcado). 19 tickets que solo tenían la fila de desayuno
  pasaron a 0 filas (correcto; se recrea al marcarlos en el ABM). Tickets que
  antes daban REFACTURAR 0 ahora dan monto real (17 → 16513.05, 46 → 16095.00,
  53 → 25936.95, 537 → 9160.00).
- Verificado con transacción + rollback: con `es_desayuno = true` la regla
  vuelve a aparecer en la evaluación.
- Backup del estado previo: `backup_20260801.ticket` (567) y
  `.ticket_procesado` (2223).

---

## 7. Pruebas de validación

Para verificar el correcto funcionamiento después del pase a producción,
probar los siguientes casos:

```sql
-- Ticket entre base y aprobación → debe dar REFACTURAR
SELECT * FROM cedir.evaluar_reintegros_por_ticket_trigger(
    (SELECT id FROM cedir.ticket WHERE protocolo ILIKE '%GZP2%' 
     AND importe_total / cedir.obtener_tipo_cambio(fecha_ticket) BETWEEN 100 AND 150 LIMIT 1)
);

-- Ticket sobre aprobación → debe dar REQUIERE APROBACION (sin REFACTURAR)
SELECT * FROM cedir.evaluar_reintegros_por_ticket_trigger(
    (SELECT id FROM cedir.ticket WHERE protocolo ILIKE '%GZP2%' 
     AND importe_total / cedir.obtener_tipo_cambio(fecha_ticket) > 150 LIMIT 1)
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
| `docs/REINTEGROS.md` | Este documento |

### Base de datos (esquema `auxiliar`)

| Objeto | Cambio |
|---|---|
| `auxiliar.evaluar_reintegros_por_ticket_trigger` | Reescrita — nueva lógica de REQUIERE APROBACION + supresión condicional de REFACTURAR; TC por fecha del ticket; sin protocolo → 0 filas |
| `auxiliar.procesar_ticket_trigger` | Corregido — parámetros de llamada, nombres de columnas, cast de nro_doc; pasa NULL para que el TC se resuelva por fecha del ticket |
| `auxiliar.protocolo_reintegro` | + UNIQUE(id_protocolo, id_reintegro), duplicados eliminados |
| `auxiliar.concepto_reintegro` | + "Reembolso de traslado (contingencia)" (cat=TRASLADO) |
| `auxiliar.monto_reintegro` | + REEMBOLSO_DIFERENCIA sin tope (valor_numerico=NULL) |
| `auxiliar.condicion_reintegro` | + "Traslado abonado por el centro" (SUPERA_MONTO, param=0) |
| `auxiliar.reintegro` | + regla de traslado contingencia (id=31) |
| `auxiliar.protocolo_reintegro` | Nuevas asignaciones: EZEF→31, GZBO→31; GZPW - LILLY→reglas copiadas desde GZPW |

### Base de datos (esquema `cedir`)

| Objeto | Cambio |
|---|---|
| `cedir.evaluar_reintegros_por_ticket_trigger` | Reemplazada por la lógica de auxiliar (REQUIERE APROBACION, TC por fecha, 0 filas sin protocolo) con JOIN a `tipo_concepto_reintegro` y **fix del pool** (`v_aplica`) |
| `cedir.concepto_reintegro` | Reemplazada por la de auxiliar (14 filas) |
| `cedir.condicion_reintegro` | Reemplazada por la de auxiliar (7 filas, sin duplicado id=7) |
| `cedir.monto_reintegro` | Reemplazada por la de auxiliar + TOPE 25 (id=31) y FIJO 80 (id=32) |
| `cedir.requisito_reintegro` | Reemplazada por la de auxiliar (16 filas) |
| `cedir.reintegro` | Reemplazada por la de auxiliar (18) + 6 nuevas (32–37) |
| `cedir.protocolo_reintegro` | Reemplazada por la de auxiliar (45) + re-mapeo de protocolos 12/15/41 (10) |
| `cedir.cotizacion_historica` | Creada y sembrada desde auxiliar; luego siembra completa de las 186 fechas de tickets (160 argentinadatos + 26 BACKUP) |
| `cedir.obtener_tipo_cambio` | Creada (histórico + 7 días + API + fallback) |
| `cedir.obtener_cotizacion_api_por_fecha` | Creada con dolarapi por fecha; **reescrita** para usar `api.argentinadatos.com` (histórico completo desde 2011) con filtro sed `/^[\[{]/,$ p` y parseo con `jsonb_array_elements` |
| `backup_20260731.ticket` / `.ticket_procesado` | Backup de seguridad previo al reproceso (567 / 889 filas) |
| `cedir.ticket` / `cedir.ticket_procesado` | Reproceso completo con `UPDATE cedir.ticket SET protocolo = protocolo` → 667 filas activas en 429 tickets |
| `cedir.evaluar_reintegros_por_ticket_trigger` | **Firma cambiada**: `importe_ticket` de `integer` a `numeric`, sin cast `::INTEGER` (preserva decimales). Se recrearon trigger function y trigger |
| `backup_20260731.ticket_procesado_decimales_pre` | Backup del estado pre-fix-decimales (1556 filas) |
| `cedir.ticket` / `auxiliar.ticket` | + columna `es_desayuno BOOLEAN DEFAULT FALSE` |
| `cedir.evaluar_reintegros_por_ticket_trigger` | + filtro: regla DESAYUNO solo aplica con `es_desayuno = true`; se recrearon trigger function y trigger |
| `models.py` / `forms.py` / `app.py` / `ticket_processor.py` | `es_desayuno` agregado al modelo, formulario, handlers y generación de INSERT |
| `templates/nuevo_ticket.html` / `editar.html` / `formulario.html` | Checkbox "Es desayuno" (y "Es traslado" en editar/formulario, que faltaban) |
| `backup_20260801.ticket` / `.ticket_procesado` | Backup pre-reproceso es_desayuno (567 / 2223 filas) |
| `cedir.ticket` / `cedir.ticket_procesado` | Reproceso es_desayuno → 448 filas activas en 410 tickets, 0 desayunos |
