# 🚀 Guía Rápida - Flujo de Sugerencias de Pacientes

## ¿Qué fue implementado?

Se ha completado el flujo para que cuando un paciente **NO sea encontrado automáticamente**, puedas:

1. ✅ Ver sugerencias de candidatos similares desde la BD
2. ✅ Seleccionar manualmente el paciente correcto
3. ✅ **INSERTAR el ticket completo en la BD** (antes solo se guardaba en sesión)

---

## 📋 Flujo de Uso

### Paso 1: Subir archivo
```
1. Ir a la página principal
2. Seleccionar una imagen o PDF
3. Hacer clic en "Subir Imagen"
```

### Paso 2: El sistema procesa
```
- ✅ Algunos pacientes: encontrados automáticamente → insertados en BD
- ⏳ Otros pacientes: no encontrados → mostrados en tabla "Pacientes no identificados"
```

### Paso 3: Seleccionar paciente manualmente
```
1. En la tabla de "Pacientes no identificados", hacer clic en "Buscar coincidencias"
2. Se abre un modal con candidatos similares
3. El modal muestra:
   - Nombre extraído del ticket
   - DNI extraído del ticket
   - Lista de candidatos con % de similitud
```

### Paso 4: Elegir el paciente correcto
```
1. Revisar los candidatos
2. Hacer clic en el que sea correcto
3. Sistema inserta automáticamente en BD
4. Modal cierra y página se recarga
5. El ticket desaparece de "Pacientes no identificados"
```

### Paso 5: Verificar
```
- El ticket ahora está en la tabla principal con:
  ✅ Paciente correcto
  ✅ Protocolo correcto
  ✅ Todos los datos del ticket extraído
```

---

## 🎨 Interfaz - Qué ves

### Modal de Selección
```
┌─────────────────────────────────────────┐
│ ❓ Paciente no identificado              │
├─────────────────────────────────────────┤
│ Datos extraídos del ticket:             │
│ ┌─────────────────┬─────────────────┐   │
│ │ Nombre: Juan    │ DNI: 12345678   │   │
│ └─────────────────┴─────────────────┘   │
│                                         │
│ Candidatos similares:                   │
│ ┌─────────────────────────────────────┐ │
│ │ Juan Pérez                   85% ✓  │ │
│ │ DNI: 12345678 | Proto: P001         │ │
│ │ Tipo: Nombre similar                │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ Juan Peréz                   78% ⚠️  │ │
│ │ DNI: 12345679 | Proto: P001         │ │
│ │ Tipo: Nombre similar                │ │
│ └─────────────────────────────────────┘ │
│                                         │
│                    [Cancelar]           │
└─────────────────────────────────────────┘
```

### Tabla de Pendientes
```
┌──────────────────────────────────────────────────┐
│ ⚠️ Pacientes no identificados (3)                │
├──┬──────────────┬──────────┬──────────────────┤
│# │ Nombre       │ DNI      │ Acción           │
├──┼──────────────┼──────────┼──────────────────┤
│1 │ Juan López   │ 12345678 │ 🔍 Buscar 🗑️   │
│2 │ María García │ 87654321 │ 🔍 Buscar 🗑️   │
│3 │ Carlos Ruiz  │ 11111111 │ 🔍 Buscar 🗑️   │
└──┴──────────────┴──────────┴──────────────────┘
```

---

## 🔧 Cambios Técnicos (Para Desarrolladores)

### Archivos Modificados:

1. **app.py**
   - `/buscar_candidatos` → mejorada con logging
   - `/seleccionar_paciente` → **AHORA INSERTA EN BD**
   - Session management → mantiene pendientes en sesión

2. **templates/abm.html**
   - Modal reformulado (más grande y claro)
   - Tabla de pendientes mejorada

3. **static/js/pacientes.js**
   - Mejor UX con loading states
   - Escapado de HTML para seguridad XSS
   - Colores dinámicos según similitud

---

## ✨ Características Nuevas

### 1. **Colores por Similitud**
```
🟢 > 80% = Verde (muy probable)
🟡 60-80% = Amarillo (posible)
🔴 < 60% = Rojo (revisar bien)
```

### 2. **Tipo de Coincidencia**
- `DNI cercano` → Se encontraron DNIs similares (±1000)
- `Nombre similar` → Se encontraron nombres parecidos

### 3. **Loading States**
- Mientras busca candidatos → spinner animado
- Mientras inserta → "Guardando selección..."
- Después de éxito → "¡Ticket guardado correctamente!"

### 4. **Auto-recarga**
- Después de seleccionar un paciente, la página se recarga automáticamente
- El ticket desaparece de "Pendientes" y aparece en el listado principal

---

## 🐛 Debugging

### Ver qué está pasando:

#### En el navegador (F12 > Network):
```
POST /buscar_candidatos
  → Busca candidatos
  
POST /seleccionar_paciente
  → Inserta ticket
```

#### En los logs del servidor:
```bash
# Buscar líneas relevantes
grep "Selección manual" /var/log/tu-app.log
grep "Ticket insertado" /var/log/tu-app.log
grep "Error" /var/log/tu-app.log
```

#### Variables de sesión:
```python
# En app.py, agregar temporalmente:
print("Pendientes en sesión:", session.get('tickets_pendientes', []))
```

---

## ⚙️ Configuración (Si necesitas cambiar algo)

### Límite de candidatos (default: 10)
```python
# En app.py, línea ~310
buscar_candidatos_similares(..., limit=10)  # Cambiar 10 a otro número
```

### Tiempo antes de recargar (default: 1.5s)
```javascript
// En pacientes.js, línea ~113
setTimeout(() => { location.reload(); }, 1500);  // Cambiar 1500 a milisegundos
```

### Umbral de similitud para colores
```javascript
// En pacientes.js, línea ~48
const similitudColor = cand.similitud > 80 ? 'success' : ...
// Cambiar 80 a otro valor
```

---

## 🧪 Prueba Rápida

### Caso de Test:
```
1. Crear un ticket con paciente = "XYZ ABC" (que NO existe)
2. Subir la imagen/PDF
3. Debería aparecer en "Pacientes no identificados"
4. Clic en "Buscar coincidencias"
5. Debería mostrar candidatos similares
6. Seleccionar uno
7. Verificar que se insertó en BD:
   - SELECT * FROM cedir.ticket WHERE paciente LIKE 'XYZ ABC%'
   - Debe tener id_paciente y protocolo rellenados
```

---

## 🔐 Seguridad

Se implementaron:
- ✅ Login requerido en ambas rutas
- ✅ Escapado de HTML (previene XSS)
- ✅ Validación de datos antes de insertar
- ✅ Logs de auditoría

---

## 📞 Próximos Pasos Opcionales

1. **Implementar botón "Eliminar" pendiente**
2. **Caché Redis** para búsquedas frecuentes
3. **Rate limiting** para evitar abuso
4. **Notificaciones en tiempo real** (WebSocket)
5. **Exportar candidatos a CSV**

---

## 📚 Documentación

- Cambios detallados: `CAMBIOS_IMPLEMENTADOS.md`
- Test de flujo: `test_flujo_seleccion.py`
- Este archivo: `GUIA_RAPIDA.md`

---

## ❓ Preguntas Frecuentes

### ¿Qué pasa si no encuentro el paciente?
```
- Si no hay candidatos similares en el modal
- Haz clic en "Cancelar"
- Luego puedes editar el ticket manualmente desde el listado
```

### ¿Se puede cambiar de opinión?
```
- Sí, puedes editar el ticket después desde el botón ✏️
- O eliminar y resubir el archivo
```

### ¿Dónde se guardan los cambios?
```
- Directamente en la base de datos (cedir.ticket)
- Se sincroniza automáticamente
```

### ¿Qué datos se pierden?
```
- NADA, todos los datos del ticket extraído se insertan
- Incluyendo el paciente seleccionado
```

---

**¡Listo para usar! 🎉**
