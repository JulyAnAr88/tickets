// main.js - Inicialización principal

document.addEventListener('DOMContentLoaded', function () {
    // Inicializar módulos
    if (typeof initTicketManagement === 'function') {
        initTicketManagement();
    }

    const pendientesContainer = document.querySelector('.card.border-warning');
    if (pendientesContainer) {
        console.log("✅ Se encontraron tickets pendientes:", pendientesContainer);
    } else {
        console.log("❌ No se encontró el bloque de tickets pendientes");
    }

    // Configurar botones de error
    const closeErrorBtn = document.getElementById('closeErrorBtn');
    const dismissErrorBtn = document.getElementById('dismissErrorBtn');
    const copyErrorBtn = document.getElementById('copyErrorBtn');

    if (closeErrorBtn) closeErrorBtn.addEventListener('click', closeErrorPanel);
    if (dismissErrorBtn) dismissErrorBtn.addEventListener('click', closeErrorPanel);
    if (copyErrorBtn) copyErrorBtn.addEventListener('click', copyErrorToClipboard);

    // Preview de imagen
    const imagenInput = document.getElementById('fileInput');
    if (imagenInput) {
        imagenInput.addEventListener('change', function (e) {
            const file = e.target.files[0];
            if (file) {
                const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'application/pdf'];
                if (!allowedTypes.includes(file.type)) {
                    alert('Tipo de archivo no permitido');
                    this.value = '';
                }
            }
        });
    }

    // Auto-cerrar alertas
    setTimeout(() => {
        document.querySelectorAll('.alert').forEach(alert => {
            const btn = alert.querySelector('.btn-close');
            if (btn) btn.click();
        });
    }, 5000);
});