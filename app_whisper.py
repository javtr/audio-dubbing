import os
import json
import threading
import re
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
        self.geometry("750x600")
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
                self.status_label.configure(text="Estado: secciones.json cargado.", text_color="#28a745")
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
            # 1. Verificar que el JSON de Gemini existe
            if not os.path.exists(METADATA_FILE):
                self.after(0, lambda: messagebox.showerror("Error", "No se encontró metadata.json. Gemini debe crearlo primero."))
                self.after(0, self._on_processing_error)
                return

            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                gemini_data = json.load(f)

            # 2. Iniciar Whisper
            try:
                model = WhisperModel("small", device="cuda", compute_type="float16")
                print("[INFO] Usando GPU (CUDA)")
            except Exception:
                model = WhisperModel("small", device="cpu", compute_type="int8")
                print("[INFO] Fallback a CPU")

            self.after(0, lambda: self.status_label.configure(text="Estado: Extrayendo tiempos por palabra..."))

            # 3. Transcribir pidiendo tiempos POR PALABRA
            # Whisper devuelve info.duration que es la duración total del audio en segundos
            segments, info = model.transcribe(audio_path, language="es", beam_size=5, word_timestamps=True)
            self.audio_duration_ms = int(info.duration * 1000)

            # 4. Aplanar todas las palabras en una lista
            whisper_words = []
            for segment in segments:
                for word in segment.words:
                    # Limpiamos puntuación para comparar fácil
                    clean_word = re.sub(r'[^\w\s]', '', word.word.lower()).strip()
                    if clean_word:
                        whisper_words.append({
                            "word": clean_word,
                            "start_ms": int(word.start * 1000)
                        })

            self.after(0, lambda: self.status_label.configure(text="Estado: Alineando textos de Gemini..."))

# 5. Algoritmo de Alineación (start_ms)
            search_index = 0
            for i, item in enumerate(gemini_data):
                original_text = item.get("original", "")
                
                # Todas las palabras de la frase actual según Gemini
                gem_words = re.sub(r'[^\w\s]', '', original_text.lower()).strip().split()
                word_count = len(gem_words) # Contamos cuántas palabras tiene la frase
                
                matched = False
                if gem_words:
                    # Buscamos alguna de las primeras 3 palabras
                    for g_word in gem_words[:3]:
                        if matched: break
                        
                        # Ampliamos el límite de búsqueda a 100 palabras por seguridad
                        limit = min(search_index + 100, len(whisper_words))
                        for j in range(search_index, limit):
                            if whisper_words[j]["word"] == g_word:
                                item["start_ms"] = whisper_words[j]["start_ms"]
                                
                                # EL FIX MAESTRO: Saltamos casi toda la frase.
                                # Restamos 3 por seguridad por si Whisper omitió alguna palabra final.
                                jump = max(1, word_count - 3)
                                search_index = j + jump  
                                
                                matched = True
                                break
                
                # Si Whisper no logró hacer match perfecto con Gemini
                if not matched:
                    print(f"[WARN] No se pudo alinear el segmento: {item['id']}")
                    # FALLBACK SEGURO: Usamos el tiempo de donde nos quedamos
                    if search_index < len(whisper_words):
                        item["start_ms"] = whisper_words[search_index]["start_ms"]
                    else:
                        item["start_ms"] = gemini_data[i-1].get("end_ms", 0)

                # ==========================================
                # REGLA DE ORO: El primer segmento SIEMPRE es 0
                # ==========================================
                if i == 0:
                    item["start_ms"] = 0

            # 5.5 Algoritmo de Cálculo de end_ms
            # Recorremos la lista para asignar el end_ms basándonos en el start_ms del siguiente
            for i in range(len(gemini_data)):
                if i < len(gemini_data) - 1:
                    # El fin de este segmento es el inicio del siguiente
                    next_start = gemini_data[i+1].get("start_ms")
                    gemini_data[i]["end_ms"] = next_start if next_start is not None else self.audio_duration_ms
                else:
                    # El fin del último segmento es el fin del audio
                    gemini_data[i]["end_ms"] = self.audio_duration_ms

            # 6. Guardar el JSON actualizado
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(gemini_data, f, indent=2, ensure_ascii=False)

            self.segments_data = gemini_data
            
            # Actualizar UI
            self.after(0, self._on_processing_finished)

        except Exception as e:
            self.after(0, lambda msg=str(e): messagebox.showerror("Error en Alineación", msg))
            self.after(0, self._on_processing_error)

    def _on_processing_finished(self):
        self.is_processing = False
        self.btn_process.configure(state="normal", text="Procesar Audio con Whisper")
        self.status_label.configure(text="¡JSON Generado con éxito!", text_color="#28a745")
        self._update_scroll_list()
        messagebox.showinfo("Éxito", f"Se han detectado {len(self.segments_data)} segmentos. Duración total analizada: {self.audio_duration_ms} ms.")

    def _on_processing_error(self):
        self.is_processing = False
        self.btn_process.configure(state="normal", text="Procesar Audio con Whisper")
        self.status_label.configure(text="Estado: Error en el proceso.", text_color="#dc3545")

    def _update_scroll_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Filtrar los que tengan start_ms como None por precaución
        valid_segs = [s for s in self.segments_data if s.get('start_ms') is not None]
        sorted_segs = sorted(valid_segs, key=lambda x: x['start_ms'])
        
        for i, seg in enumerate(sorted_segs):
            text_preview = (seg['original'][:50] + '..') if len(seg['original']) > 50 else seg['original']
            start_val = seg.get('start_ms', '???')
            end_val = seg.get('end_ms', '???')
            
            row_text = f"[{seg['id']}] | Inicio: {start_val} ms | Fin: {end_val} ms | \"{text_preview}\""
            ctk.CTkLabel(self.scroll_frame, text=row_text, anchor="w", font=("Consolas", 11)).pack(fill="x", padx=5, pady=2)

if __name__ == "__main__":
    app = WhisperAutoSegmenter()
    app.mainloop()