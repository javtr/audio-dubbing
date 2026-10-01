# Audio Dubbing Studio (AI Video Dubbing)

Sistema modular y semi-automático para doblar videos a otros idiomas usando Inteligencia Artificial (Whisper + Gemini + Pinokio CosyVoice + FFmpeg).

---

## 🚀 Inicio Rápido

Para iniciar la aplicación unificada con interfaz gráfica:

```bash
python main.py
```

---

## 🛠️ Requisitos Previos

1. **Python 3.10+** con dependencias instaladas:
   ```bash
   pip install customtkinter pygame matplotlib pydub faster-whisper gradio_client
   ```
2. **FFmpeg & FFplay:** Deben estar instalados y disponibles en el `PATH` del sistema.
3. **GPU / CUDA (Opcional pero recomendado):** Para aceleración de `faster-whisper`.
4. **Pinokio con CosyVoice:**
   - Abrir Pinokio y ejecutar la app de **CosyVoice (1.7B)** en `http://127.0.0.1:7860`.

---

## 📁 Arquitectura del Proyecto

```text
audio_dubbing/
├── assets/
│   └── clone_examples/          # Muestras de audio y transcripciones de los 4 tonos fijos
│       ├── examples.json
│       ├── ref_Conversational.wav
│       ├── ref_Explanatory.wav
│       ├── ref_Effusive.wav
│       └── ref_Serious.wav
│
├── core/                        # Lógica desacoplada
│   ├── project_manager.py       # Gestión de carpetas de proyectos y extracción con FFmpeg
│   ├── whisper_aligner.py       # Transcripción y sincronización de tiempos palabra por palabra
│   ├── pinokio_client.py        # Conexión Gradio con CosyVoice en Pinokio
│   └── audio_processor.py       # Time-stretching (atempo), mezcla y exportación
│
├── proyectos/                   # Carpeta donde vive cada video/proyecto independiente
│   └── <Nombre_Proyecto>/
│       ├── video.mp4            # Video original (si se cargó video)
│       ├── original.wav         # Pista de audio extraída
│       ├── secciones.json       # Guion, tiempos y tonos sincronizados
│       ├── audios/              # Clips de audio doblados generados por la IA
│       └── doblaje_final.wav    # Mezcla final exportada
│
└── main.py                      # Interfaz gráfica unificada Todo-en-Uno
```

---

## 🔄 Flujo de Trabajo en la Aplicación

1. **Crear / Seleccionar Proyecto:**
   - Pulsa **"➕ Nuevo"** en la barra superior.
   - Dale un nombre al proyecto y selecciona tu archivo de video (`.mp4`) o audio (`.mp3`/`.wav`).
   - El sistema extraerá automáticamente el audio original en segundo plano.

2. **Paso 1: Guion y Tiempos (`Tab 1`)**
   - Pulsa **"🎙️ Transcribir Audio"** para obtener el texto en español con Whisper.
   - Pulsa **"📋 Copiar Prompt para Gemini"** y pégalo en la web de Gemini.
   - Gemini dividirá el texto en frases lógicas, las traducirá al inglés y asignará los tonos (`Conversational`, `Explanatory`, `Effusive`, `Serious`).
   - Pega el JSON resultante en el cuadro derecho y pulsa **"💾 Guardar JSON"**.
   - Pulsa **"⏱️ Sincronizar Tiempos (Whisper)"** para calcular los milisegundos exactos de inicio y fin de cada frase.

3. **Paso 2: Doblaje con Pinokio (`Tab 2`)**
   - Revisa o ajusta las traducciones y tonos en las tarjetas de cada segmento.
   - Pulsa **"✨ Generar este"** para doblar un segmento individual o **"🚀 Solicitar Todos a Pinokio"** para generar todo el guion en lote.
   - Puedes escuchar cada audio doblado con **"🎧 Oír Doblado"**.

4. **Paso 3: Estudio y Mezcla (`Tab 3`)**
   - Visualiza las formas de onda del original y del audio doblado.
   - El sistema calcula automáticamente el factor de velocidad (**Ratio**) necesario para que cada frase en inglés encaje en el tiempo del original sin alterar el tono de voz (usando `atempo` de FFmpeg).
   - Ajusta inicios o ratios finos si lo deseas.
   - Escucha la mezcla final en tiempo real con **"▶ Reproducir Mezcla"**.
   - Exporta el resultado:
     - **"💾 Exportar Audio Doblado"** (`.wav` o `.mp3`).
     - **"🎬 Exportar Video Doblado"** (`.mp4`), que une automáticamente tu video original con la nueva pista de audio en inglés.
