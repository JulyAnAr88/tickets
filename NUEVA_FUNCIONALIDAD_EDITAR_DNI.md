# ✨ NUEVA FUNCIONALIDAD: Editar DNI/Nombre y Re-buscar

## 🎯 ¿Qué es Nuevo?

Ahora cuando abres el modal de selección de pacientes, puedes:

1. ✅ **Editar el nombre y/o DNI** que fueron extraídos del ticket
2. ✅ **Hacer clic en "Buscar de nuevo"** con los datos editados
3. ✅ **Ver nuevos candidatos** basados en los datos corregidos
4. ✅ **Seleccionar el paciente correcto** e insertar

---

## 📋 Flujo Mejorado

```
Usuario sube archivo
    ↓
Paciente no encontrado automáticamente
    ↓
Tabla muestra "Pacientes no identificados"
    ↓
Usuario hace clic en "Buscar coincidencias"
    ↓
Modal abre con:
  📝 Campo EDITABLE de Nombre
  📝 Campo EDITABLE de DNI
  🔍 Botón "Buscar de nuevo"
  📋 Lista de candidatos
    ↓
Usuario edita el DNI/Nombre si es necesario
    ↓
Usuario hace clic en "Buscar de nuevo"
    ↓
Backend busca con datos NUEVOS
    ↓
Modal muestra nuevos candidatos
    ↓
Usuario selecciona el correcto
    ↓
Ticket se inserta en BD ✅
```

---

## 💻 Ejemplo Práctico

### Escenario 1: DNI Incorrecto

```
Ticket escaneado muestra:
  Nombre: Juan García
  DNI: 12345678
  
Backend busca pero no encuentra (DNI puede estar mal leído)
  
Usuario en modal:
  1. Ve los campos de Nombre y DNI EDITABLES
  2. Corrige el DNI a: 12345678 → 12345679
  3. Hace clic en "Buscar de nuevo"
  4. Backend busca con DNI corregido
  5. Encuentra candidatos correctos
  6. Usuario selecciona "Juan García - DNI 12345679"
  7. Ticket se inserta ✅
```

### Escenario 2: Nombre Incorrecto

```
Ticket escaneado muestra:
  Nombre: Juan Garsía (error de OCR)
  DNI: 12345678

Backend busca pero no encuentra (nombre tiene error)

Usuario en modal:
  1. Ve campo de Nombre EDITABLE
  2. Corrige el nombre: "Garsía" → "García"
  3. Hace clic en "Buscar de nuevo"
  4. Backend busca con nombre corregido
  5. Encuentra al paciente correcto
  6. Usuario selecciona
  7. Ticket se inserta ✅
```

### Escenario 3: Ambos Campos Incorrectos

```
Usuario puede corregir AMBOS:
  - Nombre: Juan Garsía → Juan García
  - DNI: 12345678 → 12345679
  
Luego buscar de nuevo y encontrar el correcto
```

---

## 🎨 La Interfaz Mejorada

### Antes:
```
Nombre extraído: Juan García (solo texto)
DNI extraído: 12345678 (solo texto)
[Lista de candidatos]
```

### Ahora:
```
┌──────────────────────────────────┬──────────────────────────────────┐
│ Nombre extraído:                 │ DNI extraído:                    │
│ [Juan García        ▼]  editable │ [12345678          ▼] editable  │
└──────────────────────────────────┴──────────────────────────────────┘

[🔄 Buscar de nuevo con datos editados]

[Lista de candidatos]
```

---

## ⌨️ Cómo Usar

### Paso a Paso:

1. **Subir archivo:**
   ```
   Cargar Nueva Imagen → [Seleccionar archivo] → Subir
   ```

2. **Ver tabla de pendientes:**
   ```
   "Pacientes no identificados" aparece con lista
   ```

3. **Hacer clic en "Buscar coincidencias":**
   ```
   Modal abre automáticamente
   ```

4. **Editar si es necesario:**
   ```
   • Si DNI parece mal: editar el campo DNI
   • Si nombre parece mal: editar el campo Nombre
   • Presionar Enter o hacer clic en "Buscar de nuevo"
   ```

5. **Hacer clic en "Buscar de nuevo":**
   ```
   Modal muestra spinner
   Backend busca con datos NUEVOS
   Candidatos se actualizan
   ```

6. **Seleccionar paciente:**
   ```
   Hacer clic en un candidato
   Modal muestra "Ticket guardado correctamente"
   Página se recarga
   ```

---

## 🔍 Casos de Uso Comunes

### Caso 1: OCR Lee "2" como "8"

```
Ticket muestra: DNI 82345678
Usuario edita a: DNI 12345678
Busca de nuevo → Encuentra al paciente
```

### Caso 2: OCR Lee "G" como "O"

```
Ticket muestra: Nombre "Juan Oarcia"
Usuario edita a: Nombre "Juan García"
Busca de nuevo → Encuentra al paciente
```

### Caso 3: DNI con espacios

```
Ticket muestra: DNI "12 345 678"
Usuario edita a: DNI "12345678"
Busca de nuevo → Sistema convierte automáticamente
```

### Caso 4: Nombre incompleto

```
Ticket muestra: Nombre "Juan"
Usuario edita a: Nombre "Juan García"
Busca de nuevo → Encuentra pacientes con ese nombre completo
```

---

## 🛠️ Cambios Técnicos

### Archivo: `templates/abm.html`

```html
<!-- Cambio 1: Los campos ahora son <input> en lugar de <span> -->
<input type="text" class="form-control form-control-sm" 
    id="modalNombre" placeholder="Nombre" value="">

<input type="text" class="form-control form-control-sm" 
    id="modalDni" placeholder="DNI" value="">

<!-- Cambio 2: Nuevo botón "Buscar de nuevo" -->
<button class="btn btn-sm btn-outline-secondary w-100" 
    id="btnBuscarDeNuevo">
    <i class="bi bi-arrow-clockwise"></i> 
    Buscar de nuevo con datos editados
</button>
```

### Archivo: `static/js/pacientes.js`

```javascript
// Cambio 1: Nueva función para realizar búsquedas
function realizarBusquedaCandidatos(ticketId, nombre, dni)

// Cambio 2: Event listener para el botón "Buscar de nuevo"
btnBuscarDeNuevo.addEventListener('click', function() {
    const nombre = document.getElementById('modalNombre').value;
    const dni = document.getElementById('modalDni').value;
    realizarBusquedaCandidatos(ticketId, nombre, dni);
});

// Cambio 3: Ahora usa .value en lugar de .textContent
document.getElementById('modalNombre').value = nombre || '';
document.getElementById('modalDni').value = dni || '';
```

---

## ✅ Validaciones

```javascript
// Si no ingresas nada, el sistema avisa:
if (!nombre && !dni) {
    alert('Por favor ingresa al menos un nombre o DNI');
    return;
}
```

---

## 🎯 Ventajas

1. ✅ **Mayor flexibilidad** - Corregir errores sin eliminar el ticket
2. ✅ **Mejor UX** - Sin necesidad de recargar o volver atrás
3. ✅ **Menos pasos** - Todo en un mismo modal
4. ✅ **Más preciso** - Puedes refinar la búsqueda múltiples veces

---

## 🧪 Prueba Rápida

```
1. Subir un archivo con paciente que no se encuentre
2. Clic en "Buscar coincidencias"
3. Ver que los campos son EDITABLES (ahora son inputs)
4. Cambiar el DNI o nombre
5. Clic en "Buscar de nuevo"
6. Ver que los candidatos se actualizan
7. Seleccionar uno
8. Ticket se inserta ✅
```

---

## 🚀 Cómo Se Procesa

### En el Backend:

```python
# Antes:
@app.route('/buscar_candidatos')
def buscar_candidatos():
    data = request.get_json()
    nombre = data.get('nombre')  # Del frontend
    dni = data.get('dni')         # Del frontend
    
    # El usuario ya pudo haber editado estos valores
    candidates = protocolo_manager.buscar_candidatos_similares(
        nombre_busqueda=nombre,
        dni_busqueda=dni
    )
    return jsonify({'candidates': candidates})
```

El backend NO cambió, ya que la ruta `/buscar_candidatos` es agnóstica a si los datos fueron editados o no.

---

## 💡 Datos que se Guardan

```sql
-- Cuando seleccionas un paciente, se inserta:
INSERT INTO cedir.ticket (
    paciente,           -- Nombre + Apellido del candidato
    id_paciente,        -- ID del candidato
    protocolo,          -- Protocolo del candidato
    nro_doc,            -- DNI del candidato (DNI que usaste para buscar)
    fecha_viaje,        -- Del ticket extraído
    fecha_ticket,       -- Del ticket extraído
    distancia,          -- Del ticket extraído
    unidad,             -- Del ticket extraído
    importe_total,      -- Del ticket extraído
    pasaje,             -- Del ticket extraído
    usuario,            -- Usuario logueado
    create_time         -- NOW()
)
```

---

## 🔐 Seguridad

```javascript
// Todo input de usuario se escapa antes de mostrar:
escapeHtml(userInput)

// Ejemplo: Si alguien intenta "<script>alert('XSS')</script>"
// Se muestra como: "&lt;script&gt;alert('XSS')&lt;/script&gt;"
```

---

## 🐛 Debugging

### Si el botón "Buscar de nuevo" no funciona:

```javascript
// En consola F12:
typeof realizarBusquedaCandidatos  // Debería ser "function"
document.getElementById('btnBuscarDeNuevo')  // Debería encontrar el botón
```

### Si los campos no se editan:

```javascript
// Verificar que son inputs:
document.getElementById('modalNombre').tagName  // Debería ser "INPUT"
document.getElementById('modalDni').tagName     // Debería ser "INPUT"
```

---

## 📞 Próximas Mejoras

1. **Auto-buscar mientras escribes** (debounce + AJAX)
2. **Teclado inteligente** (seleccionar con flechas/Enter)
3. **Historial de búsquedas** (cookies)
4. **Búsqueda avanzada** (más filtros)
5. **Guardar como favorito** (para próximas veces)

---

**¡Disfruta de la búsqueda mejorada! 🎉**
