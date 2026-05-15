// pacientes.js - Selección manual de pacientes

let currentTicketId = null;
let currentTicketData = null;

function mostrarSeleccionPaciente(ticketId, nombre, dni) {
    console.log('DEBUG - ticketId:', ticketId, 'nombre:', nombre, 'dni:', dni);
    currentTicketId = ticketId;
    
    // Asignar valores a los inputs (ahora son campos editable)
    const nombreInput = document.getElementById('modalNombre');
    const dniInput = document.getElementById('modalDni');
    
    if (nombreInput) nombreInput.value = nombre || '';
    if (dniInput) dniInput.value = dni || '';

    // Mostrar spinner mientras busca
    const container = document.getElementById('candidatosList');
    if (container) {
        container.innerHTML = '<div class="text-center"><span class="spinner-border spinner-border-sm me-2"></span>Buscando candidatos similares...</div>';
    }

    // Guardar el ticket ID para la búsqueda
    const btnBuscarDeNuevo = document.getElementById('btnBuscarDeNuevo');
    if (btnBuscarDeNuevo) {
        btnBuscarDeNuevo.dataset.ticketId = ticketId;
    }

    // Realizar la búsqueda inicial
    if (nombre || dni) {
        realizarBusquedaCandidatos(ticketId, nombre, dni);
    }

    // Mostrar el modal
    const modalElement = document.getElementById('seleccionarPacienteModal');
    if (modalElement) {
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
    } else {
        console.error('Modal no encontrado: seleccionarPacienteModal');
        alert('Error: No se encontró el modal');
    }
}

function realizarBusquedaCandidatos(ticketId, nombre, dni) {
    fetch('/buscar_candidatos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket_id: ticketId, nombre: nombre, dni: dni })
    })
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('candidatosList');
            container.innerHTML = '';

            if (data.candidates?.length > 0) {
                data.candidates.forEach(cand => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'list-group-item list-group-item-action border-0 py-3 px-3 mb-2 rounded';
                    btn.style.backgroundColor = '#f8f9fa';
                    btn.style.borderLeft = '4px solid #0d6efd';
                    
                    const similitudColor = cand.similitud > 80 ? 'success' : cand.similitud > 60 ? 'warning' : 'danger';
                    
                    btn.innerHTML = `
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <strong class="d-block">${escapeHtml(cand.nombre_completo)}</strong>
                                <small class="text-muted d-block mt-1">
                                    <i class="bi bi-id-card"></i> DNI: ${escapeHtml(cand.nro_doc || 'N/A')} | 
                                    <i class="bi bi-clipboard-check"></i> Protocolo: ${escapeHtml(cand.protocolo || 'N/A')}
                                </small>
                                <small class="text-muted d-block">
                                    <i class="bi bi-info-circle"></i> Tipo: ${cand.tipo_coincidencia === 'dni_cercano' ? 'DNI cercano' : 'Nombre similar'}
                                </small>
                            </div>
                            <span class="badge bg-${similitudColor} rounded-pill ms-2 mt-1">
                                ${Math.round(cand.similitud)}%
                            </span>
                        </div>
                    `;
                    
                    btn.onclick = (e) => {
                        e.preventDefault();
                        seleccionarPaciente(ticketId, cand);
                    };
                    
                    container.appendChild(btn);
                });
            } else {
                container.innerHTML = `
                    <div class="alert alert-warning mb-0">
                        <i class="bi bi-exclamation-triangle"></i>
                        <strong>No se encontraron candidatos similares</strong>
                        <p class="mb-0 mt-2 small">Intenta editando el nombre o DNI y buscando de nuevo.</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('candidatosList').innerHTML = `
                <div class="alert alert-danger mb-0">
                    <i class="bi bi-exclamation-circle"></i> Error al buscar candidatos: ${escapeHtml(error.message)}
                </div>
            `;
        });
}

// Event listener para el botón "Buscar de nuevo"
document.addEventListener('DOMContentLoaded', function() {
    const btnBuscarDeNuevo = document.getElementById('btnBuscarDeNuevo');
    if (btnBuscarDeNuevo) {
        btnBuscarDeNuevo.addEventListener('click', function() {
            const ticketId = this.dataset.ticketId;
            const nombre = document.getElementById('modalNombre').value;
            const dni = document.getElementById('modalDni').value;
            
            if (!nombre && !dni) {
                alert('Por favor ingresa al menos un nombre o DNI');
                return;
            }
            
            // Mostrar loading mientras busca
            document.getElementById('candidatosList').innerHTML = '<div class="text-center"><span class="spinner-border spinner-border-sm me-2"></span>Buscando candidatos...</div>';
            
            realizarBusquedaCandidatos(ticketId, nombre, dni);
        });
    }
    
    // Event listeners para los botones de la tabla de pendientes (nuevo método)
    document.querySelectorAll('.btn-buscar-coincidencias').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const ticketId = parseInt(this.dataset.index);
            const nombre = this.dataset.nombre || '';
            const dni = this.dataset.dni || '';
            console.log('Botón buscar clicks:', ticketId, nombre, dni);
            mostrarSeleccionPaciente(ticketId, nombre, dni);
        });
    });
    
    document.querySelectorAll('.btn-eliminar-pendiente').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const ticketId = parseInt(this.dataset.index);
            eliminarPendiente(ticketId);
        });
    });
});

function seleccionarPaciente(ticketId, paciente) {
    console.log('seleccionarPaciente - ticketId:', ticketId, 'tipo:', typeof ticketId);
    console.log('seleccionarPaciente - paciente:', paciente);
    
    const modal = bootstrap.Modal.getInstance(document.getElementById('seleccionarPacienteModal'));
    const candidatosList = document.getElementById('candidatosList');
    
    // Deshabilitar todo y mostrar loading
    const buttons = candidatosList.querySelectorAll('button');
    buttons.forEach(btn => btn.disabled = true);
    
    candidatosList.innerHTML = '<div class="text-center"><span class="spinner-border spinner-border-sm me-2"></span>Guardando selección...</div>';

    fetch('/seleccionar_paciente', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ticket_id: ticketId,
            paciente_id: paciente.persona_id,
            nombre: paciente.nombre,
            apellido: paciente.apellido,
            protocolo: paciente.protocolo,
            nro_doc: paciente.nro_doc
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Mostrar mensaje de éxito
                candidatosList.innerHTML = `
                    <div class="alert alert-success mb-0">
                        <i class="bi bi-check-circle"></i> ¡Ticket guardado correctamente!
                        <p class="mb-0 mt-2 small">Paciente: <strong>${escapeHtml(paciente.nombre)} ${escapeHtml(paciente.apellido)}</strong></p>
                        <p class="mb-0 small">Protocolo: <strong>${escapeHtml(paciente.protocolo)}</strong></p>
                    </div>
                `;
                
                console.log('Ticket insertado exitosamente, recargando página...');
                
                setTimeout(() => {
                    // Cerrar modal primero
                    if (modal) {
                        modal.hide();
                    }
                    // Forzar recarga desde el servidor
                    window.location.reload(true);
                }, 1500);
            } else {
                throw new Error(data.message || 'Error desconocido');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            candidatosList.innerHTML = `
                <div class="alert alert-danger mb-0">
                    <i class="bi bi-exclamation-circle"></i> Error al guardar:
                    <p class="mb-0 mt-2 small">${escapeHtml(error.message)}</p>
                </div>
            `;
        });
}

function eliminarPendiente(ticketId) {
    if (!confirm('¿Estás seguro de que deseas eliminar este ticket pendiente? No se podrá recuperar.')) {
        return;
    }
    
    console.log('Eliminando ticket pendiente:', ticketId);
    
    // Llamar al servidor para eliminar el ticket pendiente
    fetch('/eliminar_pendiente', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket_index: ticketId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Mostrar mensaje de éxito
            alert('Ticket pendiente eliminado correctamente');
            // Recargar la página para actualizar el listado
            location.reload();
        } else {
            throw new Error(data.message || 'Error desconocido');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error al eliminar ticket pendiente: ' + error.message);
    });
}

// Función auxiliar para escapar HTML y evitar XSS
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const textStr = String(text);
    if (!textStr) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return textStr.replace(/[&<>"']/g, m => map[m]);
}