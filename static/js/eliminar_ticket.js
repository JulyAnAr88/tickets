// eliminar_ticket.js - Funcionalidad de eliminación de tickets

/**
 * Elimina un ticket con opción de eliminar reintegros asociados
 * @param {number} ticketId - ID del ticket a eliminar
 * @param {boolean} conReintegros - Si true, elimina también los reintegros
 */
function eliminarTicket(ticketId, conReintegros) {
    // Primero preguntar基本的 confirmación
    let mensaje = '¿Estás seguro de eliminar este ticket?';
    
    if (conReintegros) {
        mensaje += '\n\nNota: Este ticket tiene reintegros asociados. ¿Desea eliminarlos también?';
    }
    
    if (!confirm(mensaje)) {
        return;
    }
    
    // Si选择了 eliminar con reintegros, mostrar advertencia adicional
    if (conReintegros) {
        if (!confirm('⚠️ Se eliminarán también los reintegros asociados a este ticket.\n\nEsta acción no se puede deshacer.\n\n¿Continuar?')) {
            return;
        }
    }
    
    // Determinar qué endpoint usar
    let url = `/eliminar/${ticketId}`;
    if (conReintegros) {
        url = `/eliminar_con_reintegros/${ticketId}`;
    }
    
    // Realizar la eliminación
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    })
    .then(response => {
        if (response.ok) {
            // Recargar la página para actualizar el listado
            window.location.reload();
        } else {
            return response.text().then(text => {
                throw new Error(text);
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error al eliminar el ticket: ' + error.message);
    });
}

/**
 * Elimina múltiples tickets (seleccionados)
 * @param {HTMLElement} btn - Botón que disparó la acción
 */
function eliminarMultiples(btn) {
    const form = document.getElementById('deleteForm');
    const checkboxes = form.querySelectorAll('input[name="ticket_ids"]:checked');
    
    if (checkboxes.length === 0) {
        alert('No has seleccionado ningún ticket para eliminar');
        return;
    }
    
    let mensaje = `¿Estás seguro de eliminar ${checkboxes.length} ticket(s)?\n\n`;
    mensaje += '⚠️ Los tickets con reintegros asociados también se eliminarán.\n';
    mensaje += 'Esta acción no se puede deshacer.';
    
    if (!confirm(mensaje)) {
        return;
    }
    
    // Enviar el formulario
    form.submit();
}

// Funcionalidad para el botón de eliminar seleccionados
document.addEventListener('DOMContentLoaded', function() {
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', function(e) {
            e.preventDefault();
            eliminarMultiples(this);
        });
    }
});