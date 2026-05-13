// tickets.js - Selección múltiple y eliminación de tickets

function initTicketManagement() {
    const checkboxes = document.querySelectorAll('.ticket-checkbox');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    const deleteForm = document.getElementById('deleteForm');

    if (!checkboxes.length) return;

    function updateDeleteButton() {
        const checkedCount = document.querySelectorAll('.ticket-checkbox:checked').length;
        if (checkedCount > 0) {
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.innerHTML = `<i class="bi bi-trash"></i> Eliminar ${checkedCount} seleccionado${checkedCount > 1 ? 's' : ''}`;
        } else {
            deleteSelectedBtn.disabled = true;
            deleteSelectedBtn.innerHTML = '<i class="bi bi-trash"></i> Eliminar Seleccionados';
        }
    }

    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function () {
            const isChecked = this.checked;
            checkboxes.forEach(cb => cb.checked = isChecked);
            updateDeleteButton();
        });
    }

    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function () {
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            checkboxes.forEach(cb => cb.checked = !allChecked);
            if (selectAllCheckbox) selectAllCheckbox.checked = !allChecked;
            updateDeleteButton();
        });
    }

    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function () {
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            const someChecked = Array.from(checkboxes).some(cb => cb.checked);
            if (selectAllCheckbox) {
                selectAllCheckbox.checked = allChecked;
                selectAllCheckbox.indeterminate = someChecked && !allChecked;
            }
            updateDeleteButton();
        });
    });

    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', function (e) {
            e.preventDefault();
            const checkedCount = document.querySelectorAll('.ticket-checkbox:checked').length;
            if (checkedCount === 0) {
                alert('No hay tickets seleccionados');
                return;
            }
            if (confirm(`¿Eliminar ${checkedCount} ticket${checkedCount > 1 ? 's' : ''}?`)) {
                deleteForm.submit();
            }
        });
    }
}