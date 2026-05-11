#!/usr/bin/env python3
import sys
import os
from pathlib import Path

def test_pdf(pdf_path):
    """Prueba que el PDF es válido y legible"""
    
    if not os.path.exists(pdf_path):
        print(f"❌ Archivo no encontrado: {pdf_path}")
        return False
    
    print(f"✅ Archivo encontrado: {pdf_path}")
    print(f"   Tamaño: {os.path.getsize(pdf_path)} bytes")
    
    # Verificar extensión
    ext = pdf_path.split('.')[-1].lower()
    print(f"   Extensión: {ext}")
    
    if ext != 'pdf':
        print(f"⚠️ La extensión es '{ext}', no 'pdf'")
    
    # Intentar cargar con pdf2image
    try:
        from pdf2image import convert_from_path
        print("🔄 Convirtiendo PDF a imágenes...")
        images = convert_from_path(pdf_path)
        print(f"✅ PDF convertido correctamente. {len(images)} páginas")
        
        for i, img in enumerate(images):
            print(f"   Página {i+1}: {img.size[0]}x{img.size[1]} px")
        
        return True
        
    except ImportError:
        print("❌ pdf2image no está instalado. Ejecuta: pip install pdf2image")
        return False
    except Exception as e:
        print(f"❌ Error convirtiendo PDF: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_pdf(sys.argv[1])
    else:
        print("Uso: python test_pdf_upload.py /home/files/incoming/tickes-test.pdf")