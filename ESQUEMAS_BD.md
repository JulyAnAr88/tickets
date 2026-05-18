# Esquemas de Base de Datos - CEDIR

## Overview

La aplicación soporta dos esquemas de base de datos:
- **cedir**: Esquema de producción
- **auxiliar**: Esquema para desarrollo local

## Configuración

### Variable de entorno

La variable `DB_SCHEMA` en el archivo `.env` controla qué esquema se usa:

```bash
# Producción (usar cedir)
DB_SCHEMA=cedir

# Desarrollo local (usar auxiliar)
DB_SCHEMA=auxiliar
```

### Archivos de configuración

1. **.env** - Configuración activa (actualmente apunta a producción)
2. **.env.example** - Ejemplo de configuración para desarrollo

## Cómo cambiar entre esquemas

### Para desarrollo local:

1. Edita el archivo `.env`:
   ```bash
   DB_SCHEMA=auxiliar
   ```

2. O copia el archivo de ejemplo:
   ```bash
   cp .env.example .env.local
   # Edita .env.local y cambia DB_SCHEMA=auxiliar
   # Luego ejecuta: export $(cat .env.local | xargs) && python app.py
   ```

### Verificar esquema activo

Al iniciar la aplicación, verás un mensaje como:
```
🔧 Usando esquema de base de datos: cedir
```
o
```
🔧 Usando esquema de base de datos: auxiliar
```

## Estructura de esquemas

Ambos esquemas deben tener las mismas tablas:
- `ticket` - Tickets principales
- `ticket_procesado` - Reintegros asociados

El esquema `auxiliar` se puede usar para:
- Pruebas de desarrollo
- Testing de nuevas funcionalidades
- Datos de prueba sin afectar producción

## Notas

- Al hacer push al repositorio, el código siempre usará el esquema configurado en `.env`
- Para desarrollo local, usa el esquema `auxiliar` para no afectar los datos de producción
- El esquema se aplica automáticamente al iniciar la aplicación mediante `SET search_path`

## Comandos útiles

```bash
# Ver tablas en un esquema específico
psql -h localhost -U cedirssf -d cedir -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'auxiliar';"

# Cambiar esquema manualmente en PostgreSQL
SET search_path TO auxiliar;
```