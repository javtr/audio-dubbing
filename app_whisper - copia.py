import os
import json
import threading
import customtkinter as ctk
from tkinter import messagebox
from faster_whisper import WhisperModel

# ==========================================================
# CONFIGURACIÓN DE RUTAS Y VARIABLES GLOBALES
# ==========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_FOLDER = os.path.join(BASE_DIR, "files", "original")
METADATA_FILE = os.path.join(ORIGINAL_FOLDER, "secciones.json")

# Extensiones de audio soportadas
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac")

class WhisperAutoSegmenter(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración de la ventana
        self.title("Logic Imprint - Whisper Auto-Segmenter")
        self.geometry("700x600")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.segments_data = []
        self.is_processing = False
        self.audio_duration_ms = 0

        self._setup_ui()
        self._check_existing_metadata()

    def _setup_ui(self):
        # Grid configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- CABECERA ---
        self.header_label = ctk.CTkLabel(
            self, 
            text="Logic Imprint - Whisper Auto-Segmenter", 
            font=("Arial", 22, "bold")
        )
        self.header_label.grid(row=0, column=0, padx=20, pady=20)

        # --- CONTROLES ---
        self.btn_process = ctk.CTkButton(
            self, 
            text="Procesar Audio con Whisper", 
            font=("Arial", 16, "bold"),
            height=45,
            command=self.start_processing_thread
        )
        self.btn_process.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.status_label = ctk.CTkLabel(self, text="Estado: Esperando...", text_color="#aaaaaa")
        self.status_label.grid(row=2, column=0, padx=20, pady=(0, 10))

        # --- CUERPO (Scrollable Frame) ---
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Segmentos Detectados")
        self.scroll_frame.grid(row=3, column=0, padx=20, pady=20, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    def _check_existing_metadata(self):
        """Carga el JSON si ya existe para mostrar los datos actuales."""
        if os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    self.segments_data = json.load(f)
                self._update_scroll_list()
                self.status_label.configure(text="Estado: metadata.json cargado.", text_color="#28a745")
            except Exception as e:
                print(f"Error cargando JSON existente: {e}")

    def _find_audio_file(self):
        """Busca el primer archivo de audio válido en files/original/."""
        if not os.path.exists(ORIGINAL_FOLDER):
            return None
        for f in os.listdir(ORIGINAL_FOLDER):
            if f.lower().endswith(AUDIO_EXTENSIONS) and f.lower().startswith("original"):
                return os.path.join(ORIGINAL_FOLDER, f)
        return None

    def start_processing_thread(self):
        if self.is_processing:
            return
        
        audio_path = self._find_audio_file()
        if not audio_path:
            messagebox.showerror("Error", "No se encontró 'original.mp3' o '.wav' en files/original/")
            return

        self.is_processing = True
        self.btn_process.configure(state="disabled", text="Procesando...")
        self.status_label.configure(text="Estado: Iniciando modelo Whisper...", text_color="#ffc107")
        
        threading.Thread(target=self.run_whisper_logic, args=(audio_path,), daemon=True).start()

    def run_whisper_logic(self, audio_path):
        try:
            # Intentar usar CUDA si está disponible (ideal para tu RTX 4060)
            try:
                model = WhisperModel("small", device="cuda", compute_type="float16")
                print("[INFO] Usando GPU (CUDA)")
            except Exception:
                model = WhisperModel("small", device="cpu", compute_type="int8")
                print("[INFO] Fallback a CPU")

            self.after(0, lambda: self.status_label.configure(text="Estado: Transcribiendo audio..."))

            # Transcripción forzada a Español
            segments, info = model.transcribe(audio_path, language="es", beam_size=5)

            new_segments = []
            for i, segment in enumerate(segments):
                # Convertir segundos float a milisegundos int
                start_ms = int(segment.start * 1000)
                end_ms = int(segment.end * 1000)
                
                seg_dict = {
                    "id": f"seg-{i}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "original": segment.text.strip(),
                    "translated": "",
                    "tone": "",
                    "filename": f"segment_{i:03d}.wav"
                }
                new_segments.append(seg_dict)

            # Guardar JSON
            os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(new_segments, f, indent=2, ensure_ascii=False)

            self.segments_data = new_segments
            
            # Actualizar UI
            self.after(0, self._on_processing_finished)

        except Exception as e:
            self.after(0, lambda msg=str(e): messagebox.showerror("Error en Whisper", msg))
            self.after(0, self._on_processing_error)

    def _on_processing_finished(self):
        self.is_processing = False
        self.btn_process.configure(state="normal", text="Procesar Audio con Whisper")
        self.status_label.configure(text="¡JSON Generado con éxito!", text_color="#28a745")
        self._update_scroll_list()
        messagebox.showinfo("Éxito", f"Se han detectado {len(self.segments_data)} segmentos.")

    def _on_processing_error(self):
        self.is_processing = False
        self.btn_process.configure(state="normal", text="Procesar Audio con Whisper")
        self.status_label.configure(text="Estado: Error en el proceso.", text_color="#dc3545")

    def _update_scroll_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        sorted_segs = sorted(self.segments_data, key=lambda x: x['start_ms'])
        
        for i, seg in enumerate(sorted_segs):
            # Calcular fin para la visualización
            if i < len(sorted_segs) - 1:
                calculated_end = sorted_segs[i+1]['start_ms']
            else:
                calculated_end = self.audio_duration_ms if self.audio_duration_ms > 0 else "???"

            text_preview = (seg['original'][:60] + '..') if len(seg['original']) > 60 else seg['original']
            row_text = f"[{seg['id']}] | {seg['start_ms']}ms -> {calculated_end}ms | \"{text_preview}\""
            ctk.CTkLabel(self.scroll_frame, text=row_text, anchor="w", font=("Consolas", 11)).pack(fill="x", padx=5, pady=2)

if __name__ == "__main__":
    app = WhisperAutoSegmenter()
    app.mainloop()