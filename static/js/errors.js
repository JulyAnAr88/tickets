// errors.js - Manejo de errores y panel de error
// (eliminar la declaración de progressInterval)

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showErrorMessage(errorText) {
    console.log("🔴 showErrorMessage llamado con:", errorText);

    // Si errorText es un objeto, convertirlo a string legible
    if (typeof errorText === 'object') {
        let formatted = '';
        if (errorText.mensaje) formatted += `📋 ${errorText.mensaje}\n\n`;
        if (errorText.errores && errorText.errores.length > 0) {
            formatted += `🔍 Detalles:\n`;
            errorText.errores.forEach((err, i) => {
                formatted += `\n[${i + 1}] ${err.tipo || 'Error'}: ${err.mensaje || err.error || err}\n`;
                if (err.respuesta) formatted += `   Respuesta: ${err.respuesta.substring(0, 200)}...\n`;
            });
        }
        errorText = formatted || JSON.stringify(errorText, null, 2);
    }

    // Ocultar panel de carga
    const loadingPanel = document.getElementById('loadingPanel');
    if (loadingPanel) loadingPanel.style.display = 'none';

    // Detener animación - usar variable global de upload.js
    if (window.progressIntervalGlobal) clearInterval(window.progressIntervalGlobal);

    // Restaurar botón
    const submitBtn = document.getElementById('submitBtn');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-upload"></i> Subir Imagen';
    }

    // Si no hay texto de error, usar mensaje por defecto
    if (!errorText || errorText.trim() === '') {
        errorText = 'Error desconocido. Revisa los logs del servidor.';
    }

    // Formatear el error
    let formattedError = errorText;

    if (errorText.includes('500') || errorText.includes('Internal error')) {
        formattedError = `🚨 ERROR DEL SERVIDOR DE IA (500)\n\n${formattedError}\n\n📌 Solución: Reintenta en unos minutos. Si persiste, contacta al administrador.`;
    } else if (errorText.includes('JSONDecodeError')) {
        formattedError = `📄 ERROR DE FORMATO JSON\n\n${formattedError}\n\n📌 Solución: Verifica la configuración del prompt.`;
    } else if (errorText.includes('conexión') || errorText.includes('timeout')) {
        formattedError = `🌐 ERROR DE CONEXIÓN\n\n${formattedError}\n\n📌 Solución: Verifica tu conexión a internet.`;
    }

    const errorPanel = document.getElementById('errorPanel');
    const errorMessageDiv = document.getElementById('errorMessage');

    if (errorPanel && errorMessageDiv) {
        errorMessageDiv.innerHTML = `<pre class="mb-0" style="white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto;">${escapeHtml(formattedError)}</pre>`;
        errorPanel.style.display = 'block';
        errorPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

        setTimeout(() => {
            if (errorPanel.style.display !== 'none') {
                errorPanel.style.display = 'none';
            }
        }, 30000);
    } else {
        console.error("No se encontró el panel de error en el DOM");
        alert("Error: " + errorText);
    }
}

function closeErrorPanel() {
    const errorPanel = document.getElementById('errorPanel');
    if (errorPanel) errorPanel.style.display = 'none';
}

async function copyErrorToClipboard() {
    const errorMessageDiv = document.getElementById('errorMessage');
    if (errorMessageDiv) {
        const errorText = errorMessageDiv.innerText || errorMessageDiv.textContent;
        try {
            await navigator.clipboard.writeText(errorText);
            const copyBtn = document.getElementById('copyErrorBtn');
            const originalText = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="bi bi-check-lg"></i> ¡Copiado!';
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
            }, 2000);
        } catch (err) {
            console.error('Error al copiar:', err);
            alert('No se pudo copiar el error.');
        }
    }
}