// pacientes.js - Selección manual de pacientes

let currentTicketId = null;

function mostrarSeleccionPaciente(ticketId, nombre, dni) {
    currentTicketId = ticketId;
    document.getElementById('modalNombre').textContent = nombre || '(no especificado)';
    document.getElementById('modalDni').textContent = dni || '(no especificado)';

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
                    btn.className = 'list-group-item list-group-item-action';
                    btn.innerHTML = `
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <strong>${cand.nombre_completo}</strong><br>
                                <small>DNI: ${cand.nro_doc || 'N/A'} | Protocolo: ${cand.protocolo || 'N/A'}</small>
                            </div>
                            <span class="badge bg-${cand.similitud > 80 ? 'success' : 'warning'} rounded-pill">
                                ${cand.similitud}% coincidencia
                            </span>
                        </div>
                    `;
                    btn.onclick = () => seleccionarPaciente(ticketId, cand);
                    container.appendChild(btn);
                });
            } else {
                container.innerHTML = '<div class="alert alert-warning">No se encontraron candidatos similares</div>';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('candidatosList').innerHTML = '<div class="alert alert-danger">Error al buscar candidatos</div>';
        });

    new bootstrap.Modal(document.getElementById('seleccionarPacienteModal')).show();
}

function seleccionarPaciente(ticketId, paciente) {
    fetch('/seleccionar_paciente', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ticket_id: ticketId,
            paciente_id: paciente.persona_id,
            nombre: paciente.nombre,
            apellido: paciente.apellido,
            protocolo: paciente.protocolo
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) location.reload();
            else alert('Error: ' + data.message);
        });
}