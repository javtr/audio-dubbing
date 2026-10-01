import json
import os
import shutil
import sys
from gradio_client import Client, handle_file

# --- CONFIGURACIÓN DINÁMICA DE RUTAS ---
# Obtenemos la carpeta donde está este script (F:\Desarrollo\audio_dubbing)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PINOKIO_URL = "http://127.0.0.1:7860"
# Construimos rutas absolutas
REF_AUDIO_PATH = os.path.normpath(os.path.join(BASE_DIR, "files", "clone_example.wav"))
REF_TEXT_FILE = os.path.normpath(os.path.join(BASE_DIR, "files", "clone_example.txt"))
METADATA_FILE = os.path.normpath(os.path.join(BASE_DIR, "files", "metadata.json"))
OUTPUT_FOLDER = os.path.normpath(os.path.join(BASE_DIR, "doblaje_final"))

# --- VERIFICACIÓN INICIAL ---
if not os.path.exists(REF_AUDIO_PATH):
    print(f"[ERROR CRÍTICO] No se encuentra el audio de referencia en: {REF_AUDIO_PATH}")
    print("Verifica que el nombre sea exacto y que esté dentro de la carpeta 'files'.")
    sys.exit(1)

if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

def run_dubbing():
    print(f"=== INICIANDO SISTEMA DE DOBLAJE: LOGIC ANALYTICS ===")
    
    try:
        with open(REF_TEXT_FILE, "r", encoding="utf-8") as f:
            ref_text = f.read().strip()
    except Exception as e:
        print(f"[ERROR] Al leer el archivo de texto: {e}")
        return

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            segments = json.load(f)
    except Exception as e:
        print(f"[ERROR] Al leer metadata.json: {e}")
        return

    client = Client(PINOKIO_URL)
    print(f"[*] Conectado a Pinokio en {PINOKIO_URL}")

    for segment in segments:
        output_filename = segment.get("filename")
        target_text = segment.get("translated")
        
        print(f"\n[*] Procesando: {output_filename}")
        
        try:
            # Usamos handle_file con la RUTA ABSOLUTA
            result = client.predict(
                ref_audio=handle_file(REF_AUDIO_PATH),
                ref_text=ref_text,
                target_text=target_text,
                language="English",
                use_xvector_only=False,
                model_size="1.7B",
                max_chunk_chars=200,
                chunk_gap=0.0,
                seed=-1,
                api_name="/generate_voice_clone"
            )

            temp_audio_path = result[0]
            final_path = os.path.join(OUTPUT_FOLDER, output_filename)
            shutil.move(temp_audio_path, final_path)
            print(f"[OK] Generado con éxito.")

        except Exception as e:
            print
            (f"[!] Error en este segmento: {e}")

    print("\n=== PROCESO FINALIZADO ===")

if __name__ == "__main__":
    run_dubbing()