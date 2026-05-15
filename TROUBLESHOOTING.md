# ⚠️ Posibles Problemas y Soluciones

## 1. Modal no aparece o no muestra candidatos

### Síntomas:
- Haces clic en "Buscar coincidencias" pero no pasa nada
- El modal aparece pero está vacío

### Causas Posibles:
- **Sesión no tiene datos de tickets_pendientes**
- **La ruta `/buscar_candidatos` no está respondiendo**
- **Problema con la extensión `pg_trgm` de PostgreSQL**

### Soluciones:

#### Opción 1: Verificar sesión en consola (navegador)
```javascript
// En F12 > Console:
console.log(sessionStorage);
// Debería tener algo de datos
```

#### Opción 2: Ver qué retorna `/buscar_candidatos`
```javascript
// En F12 > Network:
// 1. Haz clic en "Buscar coincidencias"
// 2. Busca POST /buscar_candidatos
// 3. Mira "Response" - debería ser JSON con "candidates": [...]
```

#### Opción 3: Verificar logs del servidor
```bash
tail -f /var/log/tu-app.log | grep "buscar_candidatos"
# Debería mostrar:
# INFO: Buscando candidatos: ticket_id=1, nombre='Juan', dni='123'
# INFO: Se encontraron N candidatos
```

#### Opción 4: Verificar extensión PostgreSQL
```sql
-- En tu BD:
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';

-- Si no está instalada, hacerlo:
CREATE EXTENSION pg_trgm;
```

---

## 2. El ticket se queda pendiente después de seleccionar

### Síntomas:
- Seleccionas un paciente
- Modal dice "Ticket guardado correctamente"
- Pero al recargar sigue en "Pacientes no identificados"

### Causas:
- **INSERT falló en la BD pero el error no se mostró**
- **La sesión no se actualizó correctamente**
- **Falta un campo requerido en la tabla `cedir.ticket`**

### Soluciones:

#### 1. Ver error en logs
```bash
tail -f /var/log/tu-app.log | grep -A 5 "Error insertando"
# Verificar el mensaje de error específico
```

#### 2. Verificar estructura de tabla
```sql
-- Ver qué campos requiere la tabla:
\d cedir.ticket

-- Asegurarse de que todos estos sean opcionales (nullable):
- paciente (VARCHAR)
- id_paciente (INTEGER)
- protocolo (VARCHAR)
- fecha_viaje (DATE)
- fecha_ticket (DATE)
- distancia (INTEGER)
- unidad (VARCHAR)
- importe_total (NUMERIC)
- pasaje (VARCHAR)
- usuario (VARCHAR)
```

#### 3. Test manual de INSERT
```sql
-- Intentar insertar manualmente lo que haría el sistema:
INSERT INTO cedir.ticket (
    paciente, fecha_viaje, fecha_ticket, distancia, unidad,
    protocolo, importe_total, pasaje, create_time, usuario, id_paciente
) VALUES (
    'Juan Pérez', '2026-05-13', '2026-05-13', 50, 'KM',
    'PROTOCOL-001', 1500.00, '12345', NOW(), 'user', 42
);

-- Si falla, ver mensaje de error
```

---

## 3. El botón "Buscar coincidencias" no responde

### Síntomas:
- Haces clic pero no pasa nada
- No hay loading spinner
- Consola muestra errores

### Causas:
- **JavaScript no cargó bien**
- **Función `mostrarSeleccionPaciente()` no existe**
- **Bootstrap Modal no funciona**

### Soluciones:

#### 1. Verificar que el JS cargó
```javascript
// En F12 > Console:
typeof mostrarSeleccionPaciente
// Debería retornar: "function"

// Si retorna "undefined", significa que el JS no cargó
```

#### 2. Verificar que Bootstrap cargó
```javascript
// En F12 > Console:
typeof bootstrap
// Debería retornar: "object"

bootstrap.Modal
// Debería retornar una función
```

#### 3. Ver errores específicos
```javascript
// En F12 > Console:
// Deberías ver algún error rojo si hay problema
```

#### 4. Verificar que el modal existe
```javascript
// En F12 > Console:
document.getElementById('seleccionarPacienteModal')
// Debería retornar un elemento HTML, NO null
```

---

## 4. Los candidatos se ven feos o con colores extraños

### Síntomas:
- Modal abre pero los candidatos se ven mal formateados
- Colores incorrectos
- Texto superpuesto

### Causas:
- **CSS de Bootstrap no cargó**
- **Conflicto con otros estilos CSS**
- **Los iconos Bootstrap Icons no se cargaron**

### Soluciones:

#### 1. Verificar que Bootstrap CSS cargó
```html
<!-- En el navegador, ver source page:
Debería haber un <link> a Bootstrap CSS -->
```

#### 2. Verificar que Bootstrap Icons cargó
```html
<!-- En el navegador, ver source page:
Debería haber un <link> a Bootstrap Icons -->
```

#### 3. Limpiar caché del navegador
```bash
# En navegador:
Ctrl+Shift+Delete (Windows/Linux)
Cmd+Shift+Delete (Mac)
# Limpiar datos de navegación
```

---

## 5. Error: "Ticket pendiente no encontrado"

### Síntomas:
- Seleccionas un paciente
- Modal muestra error: "Ticket pendiente no encontrado"

### Causas:
- **El índice del ticket no coincide**
- **La sesión se limpió (timeout o múltiples pestañas)**
- **El JS está pasando ID en lugar de índice**

### Soluciones:

#### 1. Verificar que usas `ticket.index`, no `ticket.id`
```javascript
// En F12 > Console > Network > POST /seleccionar_paciente
// Ver el body enviado
// Debe tener: "ticket_id": 1 (el índice)
// NO: "ticket_id": 42 (un ID de BD)
```

#### 2. Verificar sesión en servidor
```python
# En app.py, agregar temporalmente:
@app.route('/debug/session')
def debug_session():
    return session.get('tickets_pendientes', [])
```

#### 3. No abrir múltiples pestañas
- Las sesiones pueden conflictuar
- Usa una pestaña a la vez

---

## 6. Los datos no se insertan completos

### Síntomas:
- Ticket se inserta pero algunos campos quedan vacíos
- Falta `id_paciente` o `protocolo`

### Causas:
- **Los datos extraídos no incluyen ciertos campos**
- **La estructura del `extracted_data` es diferente**
- **El `generate_insert_sql()` está filtrando campos**

### Soluciones:

#### 1. Ver qué datos viene en `extracted_data`
```python
# En app.py, línea ~350:
logger.debug(f"Extracted data: {extracted_data}")
# Buscar en logs para ver qué contiene
```

#### 2. Verificar que los campos existen
```python
# En protocolo_manager.py o app.py:
extracted_data.get('viaje', {}).get('fecha_viaje')
# Si retorna None, el campo no existe en los datos extraídos
```

#### 3. Agregar valores por defecto
```python
# En app.py, antes de insert_ticket():
if not extracted_data.get('viaje', {}).get('fecha_viaje'):
    extracted_data['viaje']['fecha_viaje'] = datetime.today()
```

---

## 7. Error de permiso: "No tienes acceso"

### Síntomas:
- Al hacer clic en "Buscar coincidencias"
- Response HTTP 401 o 403

### Causas:
- **No estás logueado**
- **Tu sesión expiró**
- **El token de Supabase es inválido**

### Soluciones:

#### 1. Verificar que estás logueado
```javascript
// En F12 > Console:
// Mira si hay algún banner de login o si el usuario está visible
```

#### 2. Re-loguearte
```
1. Ir a /login
2. Entrar con tu cuenta
3. Volver a la página de tickets
```

#### 3. Verificar token de Supabase
```python
# En app.py o supabase_helper.py:
user = supabase_helper.get_current_user()
print(user)
# Debería mostrar datos del usuario, no None
```

---

## 8. El servidor tarda demasiado en responder

### Síntomas:
- Haces clic en "Buscar coincidencias"
- Esperas 10+ segundos antes de ver candidatos
- O nunca aparecen

### Causas:
- **La BD tiene muchos registros y la búsqueda es lenta**
- **La consulta SQL es ineficiente**
- **Falta índices en la tabla `persona`**
- **El servidor está sobrecargado**

### Soluciones:

#### 1. Verificar índices en la BD
```sql
-- Ver índices en tabla persona:
SELECT * FROM pg_indexes WHERE tablename = 'persona';

-- Si no hay índices en nombre/apellido, crear:
CREATE INDEX idx_persona_nombre ON cedir.persona(nombre);
CREATE INDEX idx_persona_apellido ON cedir.persona(apellido);

-- Para búsquedas full-text (más rápidas):
CREATE INDEX idx_persona_nombre_trgm ON cedir.persona USING gin(nombre gin_trgm_ops);
CREATE INDEX idx_persona_apellido_trgm ON cedir.persona USING gin(apellido gin_trgm_ops);
```

#### 2. Verificar cantidad de registros
```sql
SELECT COUNT(*) FROM cedir.persona;
-- Si es > 1M, considerar paginar o mejorar índices
```

#### 3. Aumentar timeout en el cliente
```javascript
// En pacientes.js:
// Modificar el timeout del fetch (actualmente es 2min default)
```

---

## 9. Seguridad: Inyección SQL o XSS

### Síntomas:
- Ves caracteres extraños insertados
- Código JavaScript ejecutándose inesperadamente

### Soluciones:

✅ **Ya implementadas:**
- Parámetros con `:` en SQL (safe from SQL injection)
- Función `escapeHtml()` en JavaScript (safe from XSS)
- Login requerido en ambas rutas

⚠️ **Verificar que no rompiste:**
```python
# NO hagas esto:
sql = f"INSERT INTO ... WHERE paciente = '{nombre}'"  # ❌ VULNERABLE

# En lugar, haz:
sql = text("INSERT INTO ... WHERE paciente = :nombre")  # ✅ SEGURO
params = {'nombre': nombre}
```

```javascript
// NO hagas esto:
html = `<div>${nombre}</div>`  // ❌ VULNERABLE si nombre tiene <script>

// En lugar, haz:
html = `<div>${escapeHtml(nombre)}</div>`  // ✅ SEGURO
```

---

## 10. El modal se abre pero está fuera del viewport

### Síntomas:
- Modal aparece pero está parcialmente invisible
- No puedes ver los botones

### Causas:
- **Resolución de pantalla muy pequeña**
- **CSS que fuerza posicionamiento extraño**
- **Bootstrap no está funcando correctamente**

### Soluciones:

#### 1. Verificar en navegador
```
- Abre F12 > Device Emulation
- Prueba con diferentes tamaños de pantalla
```

#### 2. Modificar tamaño del modal
```html
<!-- En abm.html, línea ~20:
Cambiar de:
<div class="modal-dialog modal-lg">

A:
<div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
-->
```

---

## ✅ Checklist de Debugging

Cuando algo no funciona, seguir este orden:

- [ ] ¿Estoy logueado?
- [ ] ¿Los JavaScript cargaron? (F12 > Console > typeof mostrarSeleccionPaciente)
- [ ] ¿Bootstrap cargó? (F12 > Console > typeof bootstrap)
- [ ] ¿La sesión tiene datos? (Ver en servidor)
- [ ] ¿La BD responde? (Hacer SELECT manual)
- [ ] ¿Los índices existen? (Ver en BD)
- [ ] ¿Hay errores en logs? (tail -f)
- [ ] ¿Funciona en incógnito? (Sin caché)
- [ ] ¿Funciona en otro navegador? (Otro browser)
- [ ] ¿Reinicié el servidor? (Después de cambios)

---

## 📞 Si nada funciona

1. **Revisar logs completos:**
   ```bash
   tail -100 /var/log/tu-app.log | grep -E "(ERROR|Exception|Traceback)"
   ```

2. **Ejecutar test:**
   ```bash
   python3 test_flujo_seleccion.py
   ```

3. **Verificar BD directamente:**
   ```sql
   -- Ver si los candidatos existen:
   SELECT nombre, apellido FROM cedir.persona LIMIT 10;
   
   -- Ver si el último ticket se insertó:
   SELECT * FROM cedir.ticket ORDER BY create_time DESC LIMIT 1;
   ```

4. **Pedir ayuda con esta información:**
   - Pantalla del error (screenshot)
   - Últimas líneas del log
   - Versión de Python/PostgreSQL
   - Resultado de la prueba BD
