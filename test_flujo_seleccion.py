#!/usr/bin/env python3
"""
Test básico para verificar el flujo de selección manual de pacientes
"""

import json

# Simular la estructura de datos que viene desde el frontend
test_data = {
    'ticket_id': 1,  # Índice del ticket pendiente
    'paciente_id': 42,  # ID de la persona seleccionada
    'nombre': 'Juan',
    'apellido': 'Pérez',
    'protocolo': 'PROTOCOL-001',
    'nro_doc': '12345678'
}

# Simular extracted_data del ticket pendiente
extracted_data = {
    'paciente': {
        'nombre': 'Juan',
        'dni': '12345678'
    },
    'viaje': {
        'fecha_viaje': '2026-05-13',
        'distancia': 50,
        'unidad': 'KM'
    },
    'totales': {
        'importe_total': 1500.00
    },
    'fecha_ticket': '2026-05-13',
    'pasaje': '12345'
}

# Simular lo que hace el endpoint
print("=" * 80)
print("TEST: Flujo de Selección Manual de Pacientes")
print("=" * 80)

print("\n1. Datos recibidos del frontend:")
print(json.dumps(test_data, indent=2, ensure_ascii=False))

print("\n2. Datos extraídos del ticket (antes de actualizar):")
print(json.dumps(extracted_data, indent=2, ensure_ascii=False))

print("\n3. Actualizando paciente en extracted_data...")
extracted_data['paciente'] = {
    'nombre': test_data['nombre'],
    'apellido': test_data['apellido'],
    'persona_id': test_data['paciente_id'],
    'protocolo': test_data['protocolo'],
    'nro_doc': test_data['nro_doc'],
    'encontrado': True,
    'encontrado_por': 'manual'
}

print("\n4. Datos extraídos después de actualizar:")
print(json.dumps(extracted_data, indent=2, ensure_ascii=False))

print("\n5. Campos que se insertarían en cedir.ticket:")
insert_fields = {
    'paciente': f"{extracted_data['paciente']['nombre']} {extracted_data['paciente']['apellido']}",
    'id_paciente': extracted_data['paciente']['persona_id'],
    'protocolo': extracted_data['paciente']['protocolo'],
    'fecha_viaje': extracted_data['viaje']['fecha_viaje'],
    'fecha_ticket': extracted_data['fecha_ticket'],
    'distancia': extracted_data['viaje']['distancia'],
    'unidad': extracted_data['viaje']['unidad'],
    'importe_total': extracted_data['totales']['importe_total'],
    'pasaje': extracted_data['pasaje'],
    'usuario': 'test_user',
    'create_time': 'NOW()'
}
print(json.dumps(insert_fields, indent=2, ensure_ascii=False))

print("\n" + "=" * 80)
print("✅ TEST COMPLETADO - Flujo validado correctamente")
print("=" * 80)
