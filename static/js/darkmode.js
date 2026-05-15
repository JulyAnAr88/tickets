/**
 * Sistema de Modo Oscuro y Claro
 * Gestiona el cambio de temas con persistencia en localStorage
 */

// Detectar si el usuario prefiere modo oscuro
function detectSystemPreference() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

// Obtener el tema guardado del localStorage
function getSavedTheme() {
    return localStorage.getItem('theme-mode');
}

// Guardar preferencia de tema en localStorage
function saveTheme(theme) {
    localStorage.setItem('theme-mode', theme);
}

// Aplicar el tema
function applyTheme(theme) {
    const html = document.documentElement;
    
    // Agregar transición suave
    html.style.transition = 'background-color 0.3s ease, color 0.3s ease';
    
    if (theme === 'dark') {
        html.classList.add('dark-mode');
        updateThemeButton(true);
    } else {
        html.classList.remove('dark-mode');
        updateThemeButton(false);
    }
    
    // Remover transición después de que se complete
    setTimeout(() => {
        html.style.transition = '';
    }, 300);
}

// Actualizar el ícono del botón
function updateThemeButton(isDarkMode) {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        const icon = themeToggle.querySelector('i');
        if (isDarkMode) {
            icon.classList.remove('bi-sun-fill');
            icon.classList.add('bi-moon-fill');
            themeToggle.setAttribute('title', 'Cambiar a modo claro');
            themeToggle.setAttribute('aria-label', 'Cambiar a modo claro');
        } else {
            icon.classList.remove('bi-moon-fill');
            icon.classList.add('bi-sun-fill');
            themeToggle.setAttribute('title', 'Cambiar a modo oscuro');
            themeToggle.setAttribute('aria-label', 'Cambiar a modo oscuro');
        }
    }
}

// Inicializar tema
function initializeTheme() {
    let savedTheme = getSavedTheme();
    
    // Si no hay tema guardado, usar preferencia del sistema
    if (!savedTheme) {
        savedTheme = detectSystemPreference() ? 'dark' : 'light';
    }
    
    applyTheme(savedTheme);
}

// Alternar entre temas
function toggleTheme() {
    const html = document.documentElement;
    const isDarkMode = html.classList.contains('dark-mode');
    const newTheme = isDarkMode ? 'light' : 'dark';
    
    applyTheme(newTheme);
    saveTheme(newTheme);
}

// Configurar event listeners cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    // Inicializar tema
    initializeTheme();
    
    // Agregar event listener al botón de toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // Escuchar cambios en la preferencia del sistema
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            // Solo aplicar si el usuario no ha guardado una preferencia
            if (!getSavedTheme()) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }
});
