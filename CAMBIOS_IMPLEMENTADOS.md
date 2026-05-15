# 📋 Cambios Implementados - Flujo de Sugerencias de Pacientes

## 🎯 Objetivo
Implementar un flujo completo para que cuando un paciente no sea reconocido automáticamente, el usuario pueda:
1. Ver sugerencias de candidatos similares desde la BD
2. Seleccionar el paciente correcto manualmente
3. Insertar el ticket completo con todos los datos

---

## ✅ Cambios Realizados

### 1. **app.py** - Backend

#### Cambio 1: Ruta `/buscar_candidatos` mejorada (línea 298-323)
```python
@app.route('/buscar_candidatos', methods=['POST'])
@supabase_helper.login_required
def buscar_candidatos():
```

**Mejoras:**
- ✅ Agregado decorador `@supabase_helper.login_required`
- ✅ Mejor logging con detalles de búsqueda
- ✅ Respuesta JSON mejorada con `success` flag
- ✅ Manejo de errores más robusto
- ✅ Limit de resultados fijo en 10

#### Cambio 2: Ruta `/seleccionar_paciente` completamente reformulada (línea 323-402)
```python
@app.route('/seleccionar_paciente', methods=['POST'])
@supabase_helper.login_required
def seleccionar_paciente():
```

**Lo que hace ahora:**
1. Obtiene los datos extraídos del ticket desde `session['tickets_pendientes']`
2. Actualiza los datos del paciente con la selección manual
3. **INSERTA el ticket completo en `cedir.ticket`** (antes solo actualizaba)
4. Remueve el ticket de `tickets_pendientes` en sesión
5. Retorna información sobre tickets pendientes restantes

**Cambios principales:**
- ✅ Usa `generate_insert_sql()` para generar SQL correcto
- ✅ Usa `insert_ticket()` para insertar en BD
- ✅ Mantiene `extracted_data` íntegro con nuevos datos del paciente
- ✅ Logging detallado en cada paso
- ✅ Retorna `remaining_pending` para actualizar UI

#### Cambio 3: Gestión de sesión mejorada (línea 245-248)
```python
# Cambio de: session.pop('tickets_pendientes', [])
# A: session.get('tickets_pendientes', [])
```

**Razón:** Los tickets_pendientes deben persistir en sesión hasta que se completen, no desaparecer después de la primera carga.

---

### 2. **templates/abm.html** - Frontend HTML

#### Cambio 1: Modal reformulado (línea 17-43)
```html
<div class="modal fade" id="seleccionarPacienteModal" tabindex="-1">
```

**Mejoras visuales:**
- ✅ Cambio de tamaño: `modal-dialog` → `modal-lg`
- ✅ Cards para mostrar datos extraídos
- ✅ Mejor estructura con headers y separadores
- ✅ Información más clara y organizada

#### Cambio 2: Panel de tickets pendientes mejorado (línea 136-177)
```html
<!-- ========== TICKETS PENDIENTES ========== -->
```

**Mejoras:**
- ✅ Tabla más clara con estilos mejorados
- ✅ Agregado botón "Eliminar" para cada pendiente
- ✅ Mejor visualización con badges y colores
- ✅ Información de sesión sobre qué falta

---

### 3. **static/js/pacientes.js** - Frontend JavaScript

#### Cambio 1: Función `mostrarSeleccionPaciente()` mejorada
```javascript
function mostrarSeleccionPaciente(ticketId, nombre, dni)
```

**Mejoras:**
- ✅ Loading spinner mientras busca
- ✅ Colores dinámicos según similitud (success/warning/danger)
- ✅ Información del tipo de coincidencia (DNI cercano / Nombre similar)
- ✅ Mejor presentación con `border-left` y estilos mejorados
- ✅ Escapado de HTML para prevenir XSS

#### Cambio 2: Función `seleccionarPaciente()` mejorada
```javascript
function seleccionarPaciente(ticketId, paciente)
```

**Mejoras:**
- ✅ Deshabilita botones durante procesamiento
- ✅ Muestra loading state
- ✅ Manejo de error/éxito diferenciado
- ✅ Recarga automática después de éxito
- ✅ Timeout de 1.5s antes de recargar (permite ver mensaje)

#### Cambio 3: Nueva función `eliminarPendiente()`
```javascript
function eliminarPendiente(ticketId)
```

**Nota:** Por ahora muestra un placeholder. La implementación completa puede agregarse en v2.

#### Cambio 4: Función `escapeHtml()` para seguridad
```javascript
function escapeHtml(text)
```

**Razón:** Prevenir XSS attacks cuando se muestran nombres de pacientes.

---

## 🔄 Flujo Completo Ahora Es:

```
1. Usuario sube archivo (imagen o PDF)
   ↓
2. Backend procesa con IA:
   - Algunos tickets: paciente encontrado → inserción automática ✅
   - Otros tickets: paciente no encontrado → guardados en session como "pendientes"
   ↓
3. Frontend muestra tabla de "Pacientes no identificados"
   ↓
4. Usuario hace click en "Buscar coincidencias"
   ↓
5. Frontend llama POST /buscar_candidatos
   ↓
6. Backend retorna lista de candidatos similares
   ↓
7. Modal muestra candidatos con % de similitud
   ↓
8. Usuario selecciona un candidato
   ↓
9. Frontend llama POST /seleccionar_paciente
   ↓
10. Backend:
    - Obtiene datos extraídos del ticket
    - Actualiza con paciente seleccionado
    - INSERTA en cedir.ticket ✨
    - Remueve de tickets_pendientes
   ↓
11. Frontend muestra "Ticket guardado correctamente"
   ↓
12. Recarga página automáticamente
   ↓
13. Ticket desaparece de tabla de pendientes
   ↓
14. ✅ Ticket está en BD con todos los datos

```

---

## 📊 Datos que se Insertan

Cuando el usuario selecciona un paciente manualmente, se inserta:

| Campo | Origen |
|-------|--------|
| `paciente` | Nombre + Apellido seleccionado |
| `id_paciente` | ID de la persona seleccionada |
| `protocolo` | Protocolo del paciente seleccionado |
| `nro_doc` | DNI del paciente seleccionado |
| `fecha_viaje` | Del ticket extraído |
| `fecha_ticket` | Del ticket extraído |
| `distancia` | Del ticket extraído |
| `unidad` | Del ticket extraído |
| `importe_total` | Del ticket extraído |
| `pasaje` | Del ticket extraído |
| `usuario` | Usuario logueado |
| `create_time` | NOW() (timestamp actual) |

---

## 🔐 Seguridad Implementada

1. ✅ **Decorador `@supabase_helper.login_required`** en ambas rutas
2. ✅ **Escapado de HTML** en JavaScript (función `escapeHtml()`)
3. ✅ **Validación de datos** antes de insertar
4. ✅ **Logs detallados** para auditoría
5. ✅ **Verificación de sesión** antes de insertar

---

## 📝 Logging Agregado

Se agregó logging extenso para debugging:

```python
logger.info(f"📋 Selección manual de paciente: ticket_index={ticket_index}...")
logger.debug(f"Tickets pendientes en sesión: {len(tickets_pendientes)}")
logger.info(f"✏️ Paciente actualizado en extracted_data: {nombre} {apellido}")
logger.info(f"✅ Ticket insertado manualmente: {nombre} {apellido}")
```

Útil para:
- Debug de problemas
- Auditoría de cambios
- Seguimiento de errores

---

## 🧪 Cómo Probar

### Test Manual:
1. Subir un archivo con un paciente que NO esté en BD
2. Debería aparecer en "Pacientes no identificados"
3. Hacer click en "Buscar coincidencias"
4. Debería mostrar modal con candidatos similares
5. Seleccionar un candidato
6. Debería mostrar "Ticket guardado correctamente"
7. Verificar en BD que el ticket se insertó con `id_paciente` y `protocolo` correctos

### Test en Logs:
```bash
tail -f /var/log/tu-app.log | grep -E "(Selección manual|Ticket insertado)"
```

---

## 🚀 Próximas Mejoras (Opcional)

1. **Implementar eliminación de pendientes** en `/eliminar_pendiente`
2. **Caché Redis** para búsquedas frecuentes de pacientes
3. **Rate limiting** para `/buscar_candidatos`
4. **Notificaciones en tiempo real** (WebSocket) cuando se completa
5. **Export de candidatos** a CSV para análisis
6. **Búsqueda avanzada** con más filtros

---

## 📞 Soporte

Si tienes dudas sobre algún cambio específico, revisa:
- **Logs en `/var/log/`** para entender qué está pasando
- **Navegador (F12 > Network)** para ver requests/responses
- **Variables de sesión** imprimiendo `session.get('tickets_pendientes')`
