// upload.js - Carga de imágenes y barra de progreso

// Usar variable global para el intervalo
window.progressIntervalGlobal = null;
let progressValue = 0;

function showLoading() {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files || fileInput.files.length === 0) {
        alert('Por favor, seleccione un archivo primero');
        return false;
    }

    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Procesando...';

    const loadingPanel = document.getElementById('loadingPanel');
    if (loadingPanel) loadingPanel.style.display = 'block';

    const progressBar = document.querySelector('#loadingPanel .progress-bar');
    if (progressBar) {
        progressValue = 0;
        progressBar.style.width = '0%';

        if (window.progressIntervalGlobal) clearInterval(window.progressIntervalGlobal);
        
        window.progressIntervalGlobal = setInterval(() => {
            if (progressValue < 90) {
                progressValue += 10;
                progressBar.style.width = progressValue + '%';

                const loadingMessage = document.getElementById('loadingMessage');
                if (loadingMessage) {
                    if (progressValue === 20) loadingMessage.textContent = 'Analizando imagen...';
                    else if (progressValue === 40) loadingMessage.textContent = 'Extrayendo texto con IA...';
                    else if (progressValue === 60) loadingMessage.textContent = 'Identificando datos del ticket...';
                    else if (progressValue === 80) loadingMessage.textContent = 'Validando información...';
                }
            }
        }, 800);
    }
    return true;
}

async function handleSubmit(event) {
    event.preventDefault();

    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files || fileInput.files.length === 0) {
        alert('Por favor, seleccione un archivo primero');
        return false;
    }

    showLoading();
    const formData = new FormData(event.target);

    try {
        const response = await fetch(event.target.action, { method: 'POST', body: formData });
        const text = await response.text();

        if (!response.ok) {
            let errorMsg = `Error HTTP ${response.status}: ${response.statusText}`;
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = text;
            const flashMessage = tempDiv.querySelector('.alert-danger');
            if (flashMessage) errorMsg = flashMessage.innerText;
            if (typeof showErrorMessage === 'function') showErrorMessage(errorMsg);
            else alert("Error: " + errorMsg);
            return false;
        }

        window.location.href = window.location.href;
        return true;
    } catch (error) {
        console.error('Error de red:', error);
        if (typeof showErrorMessage === 'function') {
            showErrorMessage(`Error de conexión: ${error.message}`);
        } else {
            alert(`Error de conexión: ${error.message}`);
        }
        return false;
    }
}