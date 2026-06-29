let pollInterval = null;

document.addEventListener('DOMContentLoaded', function () {
    const taskId = document.getElementById('processingTaskId');
    if (taskId && taskId.value) {
        startPolling(taskId.value);
    }
});

function startPolling(taskId) {
    const loadingPanel = document.getElementById('loadingPanel');
    if (loadingPanel) loadingPanel.style.display = 'block';

    const submitBtn = document.getElementById('submitBtn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Procesando...';
    }

    const progressBar = document.querySelector('#loadingPanel .progress-bar');
    let progressValue = 10;

    if (progressBar) {
        progressBar.style.width = '10%';
    }

    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch('/abm/task_status/' + taskId);
            const data = await resp.json();

            if (progressBar && progressValue < 90) {
                progressValue += 5;
                progressBar.style.width = progressValue + '%';
            }

            const loadingMessage = document.getElementById('loadingMessage');

            if (data.state === 'PENDING') {
                if (loadingMessage) loadingMessage.textContent = 'Esperando para procesar...';
            } else if (data.state === 'STARTED') {
                if (loadingMessage) loadingMessage.textContent = 'Extrayendo datos del ticket...';
            } else if (data.state === 'SUCCESS') {
                clearInterval(pollInterval);
                if (progressBar) progressBar.style.width = '100%';
                if (loadingMessage) loadingMessage.textContent = 'Procesamiento completado';
                await finalizeTask(taskId);
            } else if (data.state === 'FAILURE') {
                clearInterval(pollInterval);
                if (loadingMessage) loadingMessage.textContent = 'Error en procesamiento';
                if (typeof showErrorMessage === 'function') {
                    showErrorMessage('Error al procesar: ' + (data.error || 'Error desconocido'));
                }
                if (progressBar) {
                    progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                    progressBar.classList.add('bg-danger');
                }
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="bi bi-upload"></i> Subir Imagen';
                }
            }
        } catch (err) {
            console.error('Error polling task status:', err);
        }
    }, 2000);
}

async function finalizeTask(taskId) {
    try {
        const resp = await fetch('/abm/finalize_task/' + taskId, { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            window.location.href = '/abm';
        }
    } catch (err) {
        console.error('Error finalizing task:', err);
        window.location.href = '/abm';
    }
}

function showLoading() {
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

        if (response.redirected) {
            window.location.href = response.url;
            return true;
        }

        const text = await response.text();
        if (!response.ok) {
            let errorMsg = 'Error HTTP ' + response.status;
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = text;
            const flashMessage = tempDiv.querySelector('.alert-danger');
            if (flashMessage) errorMsg = flashMessage.innerText;
            if (typeof showErrorMessage === 'function') showErrorMessage(errorMsg);
            else alert('Error: ' + errorMsg);
            return false;
        }

        window.location.href = window.location.href;
        return true;
    } catch (error) {
        console.error('Error de red:', error);
        if (typeof showErrorMessage === 'function') {
            showErrorMessage('Error de conexión: ' + error.message);
        } else {
            alert('Error de conexión: ' + error.message);
        }
        return false;
    }
}
