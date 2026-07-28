let protocoloId = null;
let reglas = [];

document.addEventListener('DOMContentLoaded', function () {
    const protocoloSelect = document.getElementById('protocoloSelect');
    const btnAgregar = document.getElementById('btnAgregarRegla');
    const reglaForm = document.getElementById('reglaForm');
    const btnConfirmarEliminar = document.getElementById('btnConfirmarEliminar');

    protocoloSelect.addEventListener('change', function () {
        protocoloId = this.value;
        btnAgregar.disabled = !protocoloId;
        if (protocoloId) {
            cargarReglas(protocoloId);
        } else {
            document.getElementById('noSelectionRow').style.display = '';
            document.getElementById('loadingRow').style.display = 'none';
            document.getElementById('emptyRow').style.display = 'none';
            document.getElementById('reglasBody').querySelectorAll('tr.dynamic-row').forEach(r => r.remove());
        }
    });

    btnAgregar.addEventListener('click', function () {
        abrirModal(null);
    });

    reglaForm.addEventListener('submit', function (e) {
        e.preventDefault();
        guardarRegla();
    });

    btnConfirmarEliminar.addEventListener('click', function () {
        const idp = this.dataset.idProtocolo;
        const idr = this.dataset.idReintegro;
        if (idp && idr) eliminarRegla(idp, idr);
    });

    const conceptoSelect = document.getElementById('conceptoSelect');
    conceptoSelect.addEventListener('change', function () {
        const opt = this.options[this.selectedIndex];
        document.getElementById('conceptoCategoria').textContent = opt ? opt.dataset.categoria || '-' : '-';
    });

    const condicionSelect = document.getElementById('condicionSelect');
    condicionSelect.addEventListener('change', function () {
        const opt = this.options[this.selectedIndex];
        document.getElementById('condicionTipo').textContent = opt ? opt.dataset.tipo || '-' : '-';
    });
});

function cargarReglas(protocoloId) {
    document.getElementById('noSelectionRow').style.display = 'none';
    document.getElementById('loadingRow').style.display = '';
    document.getElementById('emptyRow').style.display = 'none';
    document.getElementById('reglasBody').querySelectorAll('tr.dynamic-row').forEach(r => r.remove());

    fetch(`/abm/reintegros/api/listar/${protocoloId}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('loadingRow').style.display = 'none';
            if (data.error) { mostrarError(data.error); return; }
            reglas = data.reglas || [];
            const tbody = document.getElementById('reglasBody');
            if (reglas.length === 0) {
                document.getElementById('emptyRow').style.display = '';
                return;
            }
            reglas.forEach(r => {
                const tr = document.createElement('tr');
                tr.className = 'dynamic-row';
                tr.innerHTML = `
                    <td>${r.id_reintegro}</td>
                    <td>${escapeHtml(r.concepto)}</td>
                    <td><span class="badge bg-info">${escapeHtml(r.categoria)}</span></td>
                    <td>${escapeHtml(r.tipo_codigo)}</td>
                    <td>${r.parametro_evaluacion != null ? r.parametro_evaluacion : '-'}</td>
                    <td>${escapeHtml(r.monto_tipo)}</td>
                    <td>${r.monto_valor != null ? r.monto_valor : '-'}${r.monto_unidad ? ' ' + r.monto_unidad : ''}</td>
                    <td>${escapeHtml(r.requisito || '-')}</td>
                    <td>
                        <button class="btn btn-sm btn-danger" onclick="confirmarEliminar(${r.id_protocolo}, ${r.id_reintegro}, '${escapeHtml(r.concepto)}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => {
            document.getElementById('loadingRow').style.display = 'none';
            mostrarError('Error al cargar reglas: ' + err.message);
        });
}

function abrirModal(regla) {
    document.getElementById('editReintegroId').value = regla ? regla.id_reintegro : '';
    document.getElementById('modalTitle').textContent = regla ? 'Editar regla' : 'Agregar regla';
    document.getElementById('conceptoSelect').value = regla ? regla.id_concepto : '';
    document.getElementById('condicionSelect').value = regla ? regla.id_condicion : '';
    document.getElementById('montoSelect').value = regla ? regla.id_monto : '';
    document.getElementById('requisitoSelect').value = regla ? (regla.id_requisito || '') : '';
    const conceptoOpt = document.getElementById('conceptoSelect').options[document.getElementById('conceptoSelect').selectedIndex];
    document.getElementById('conceptoCategoria').textContent = conceptoOpt ? conceptoOpt.dataset.categoria || '-' : '-';
    const condicionOpt = document.getElementById('condicionSelect').options[document.getElementById('condicionSelect').selectedIndex];
    document.getElementById('condicionTipo').textContent = condicionOpt ? condicionOpt.dataset.tipo || '-' : '-';
    const modal = new bootstrap.Modal(document.getElementById('reglaModal'));
    modal.show();
}

function guardarRegla() {
    const data = {
        id_protocolo: protocoloId,
        id_reintegro: document.getElementById('editReintegroId').value || null,
        id_concepto: document.getElementById('conceptoSelect').value,
        id_condicion: document.getElementById('condicionSelect').value,
        id_monto: document.getElementById('montoSelect').value,
        id_requisito: document.getElementById('requisitoSelect').value || null
    };
    if (!data.id_concepto || !data.id_condicion || !data.id_monto) {
        alert('Completá los campos obligatorios: Concepto, Condición y Monto.');
        return;
    }
    const btn = document.getElementById('btnGuardar');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Guardando...';

    const url = data.id_reintegro
        ? `/abm/reintegros/api/editar/${data.id_reintegro}`
        : '/abm/reintegros/api/agregar';

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
        .then(r => r.json())
        .then(result => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-circle"></i> Guardar';
            if (result.error) {
                alert('Error: ' + result.error);
                return;
            }
            const modal = bootstrap.Modal.getInstance(document.getElementById('reglaModal'));
            modal.hide();
            cargarReglas(protocoloId);
        })
        .catch(err => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-circle"></i> Guardar';
            alert('Error de red: ' + err.message);
        });
}

function confirmarEliminar(idp, idr, concepto) {
    document.getElementById('eliminarInfo').textContent = `Regla: ${concepto}`;
    document.getElementById('btnConfirmarEliminar').dataset.idProtocolo = idp;
    document.getElementById('btnConfirmarEliminar').dataset.idReintegro = idr;
    const modal = new bootstrap.Modal(document.getElementById('eliminarModal'));
    modal.show();
}

function eliminarRegla(idp, idr) {
    const btn = document.getElementById('btnConfirmarEliminar');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Eliminando...';

    fetch('/abm/reintegros/api/eliminar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id_protocolo: parseInt(idp), id_reintegro: parseInt(idr) })
    })
        .then(r => r.json())
        .then(result => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-trash"></i> Eliminar';
            const modal = bootstrap.Modal.getInstance(document.getElementById('eliminarModal'));
            modal.hide();
            if (result.error) {
                alert('Error: ' + result.error);
                return;
            }
            cargarReglas(protocoloId);
        })
        .catch(err => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-trash"></i> Eliminar';
            alert('Error de red: ' + err.message);
        });
}

function mostrarError(msg) {
    const tbody = document.getElementById('reglasBody');
    const tr = document.createElement('tr');
    tr.className = 'dynamic-row';
    tr.innerHTML = `<td colspan="9" class="text-center text-danger py-3"><i class="bi bi-exclamation-circle"></i> ${escapeHtml(msg)}</td>`;
    tbody.appendChild(tr);
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
