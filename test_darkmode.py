#!/usr/bin/env python3
"""
Test de validación para la implementación de Modo Oscuro y Claro en el proyecto real
Verifica que todos los archivos estén correctamente creados y modificados
"""

import os
import re
from pathlib import Path

def test_darkmode_implementation():
    """Realiza pruebas de validación de la implementación"""
    
    project_root = Path("/home/july/Desarrollos/Gestión-tickets")
    tests_passed = 0
    tests_failed = 0
    
    print("=" * 60)
    print("🧪 Validando Implementación de Modo Oscuro y Claro (Proyecto Real)")
    print("=" * 60)
    
    # Test 1: Verificar que darkmode.js existe
    print("\n[Test 1] Verificando que darkmode.js existe...")
    darkmode_js = project_root / "static" / "js" / "darkmode.js"
    if darkmode_js.exists():
        print("✅ darkmode.js existe")
        tests_passed += 1
    else:
        print("❌ darkmode.js NO existe")
        tests_failed += 1
    
    # Test 2: Verificar contenido de darkmode.js
    print("\n[Test 2] Verificando contenido de darkmode.js...")
    required_functions = [
        'detectSystemPreference',
        'getSavedTheme',
        'saveTheme',
        'applyTheme',
        'updateThemeButton',
        'toggleTheme',
        'initializeTheme'
    ]
    
    if darkmode_js.exists():
        content = darkmode_js.read_text()
        missing_functions = [f for f in required_functions if f'function {f}' not in content]
        
        if not missing_functions:
            print("✅ Todas las funciones requeridas están presentes")
            tests_passed += 1
        else:
            print(f"❌ Funciones faltantes: {missing_functions}")
            tests_failed += 1
    
    # Test 3: Verificar que base.html incluye darkmode.js
    print("\n[Test 3] Verificando que base.html incluye darkmode.js...")
    base_html = project_root / "templates" / "base.html"
    if base_html.exists():
        content = base_html.read_text()
        if 'darkmode.js' in content:
            print("✅ base.html incluye darkmode.js")
            tests_passed += 1
        else:
            print("❌ base.html NO incluye darkmode.js")
            tests_failed += 1
    
    # Test 4: Verificar que base.html tiene el botón toggle
    print("\n[Test 4] Verificando que base.html tiene el botón toggle...")
    if base_html.exists():
        content = base_html.read_text()
        if 'theme-toggle' in content and 'btn-theme-toggle' in content:
            print("✅ base.html tiene el botón toggle")
            tests_passed += 1
        else:
            print("❌ base.html NO tiene el botón toggle")
            tests_failed += 1
    
    # Test 5: Verificar que style.css tiene variables para modo oscuro
    print("\n[Test 5] Verificando variables CSS para modo oscuro...")
    style_css = project_root / "static" / "css" / "style.css"
    if style_css.exists():
        content = style_css.read_text()
        dark_mode_count = content.count('html.dark-mode')
        
        if dark_mode_count > 10:
            print(f"✅ style.css tiene {dark_mode_count} definiciones para modo oscuro")
            tests_passed += 1
        else:
            print(f"❌ style.css tiene muy pocas definiciones para modo oscuro ({dark_mode_count})")
            tests_failed += 1
    
    # Test 6: Verificar que style.css tiene variables CSS
    print("\n[Test 6] Verificando variables CSS en style.css...")
    if style_css.exists():
        content = style_css.read_text()
        if '--bg-body' in content and '--color-text' in content:
            print("✅ style.css tiene variables CSS dinámicas")
            tests_passed += 1
        else:
            print("❌ style.css NO tiene todas las variables CSS dinámicas")
            tests_failed += 1
    
    # Test 7: Verificar que style.css tiene estilos para btn-theme-toggle
    print("\n[Test 7] Verificando estilos para btn-theme-toggle...")
    if style_css.exists():
        content = style_css.read_text()
        if '.btn-theme-toggle' in content:
            print("✅ style.css tiene estilos para btn-theme-toggle")
            tests_passed += 1
        else:
            print("❌ style.css NO tiene estilos para btn-theme-toggle")
            tests_failed += 1
    
    # Test 8: Verificar que darkmode.js usa localStorage
    print("\n[Test 8] Verificando uso de localStorage en darkmode.js...")
    if darkmode_js.exists():
        content = darkmode_js.read_text()
        if 'localStorage' in content:
            print("✅ darkmode.js usa localStorage para persistencia")
            tests_passed += 1
        else:
            print("❌ darkmode.js NO usa localStorage")
            tests_failed += 1
    
    # Test 9: Verificar documentación
    print("\n[Test 9] Verificando archivos de documentación...")
    docs = [
        project_root / "DARKMODE_IMPLEMENTATION.md"
    ]
    
    doc_count = sum(1 for doc in docs if doc.exists())
    if doc_count == len(docs):
        print(f"✅ Archivo de documentación está presente ({doc_count})")
        tests_passed += 1
    else:
        print(f"⚠️  Solo {doc_count}/{len(docs)} archivos de documentación están presentes")
    
    # Resumen
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE PRUEBAS")
    print("=" * 60)
    print(f"✅ Pruebas pasadas: {tests_passed}")
    print(f"❌ Pruebas fallidas: {tests_failed}")
    total = tests_passed + tests_failed
    percentage = (tests_passed / total * 100) if total > 0 else 0
    print(f"📈 Tasa de éxito: {percentage:.1f}%")
    
    if tests_failed == 0:
        print("\n🎉 ¡IMPLEMENTACIÓN COMPLETADA CON ÉXITO!")
        return True
    else:
        print("\n⚠️  Hay algunos problemas que revisar")
        return False

if __name__ == "__main__":
    success = test_darkmode_implementation()
    exit(0 if success else 1)
