import os
import json
import shutil
import threading
import io
from tkinter import messagebox
import customtkinter as ctk
from gradio_client import Client, handle_file
from pydub import AudioSegment
import pygame

# ==========================================================
# CONFIGURACIÓN DE RUTAS RELATIVAS Y CONSTANTES GLOBALES
# ==========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PATH_CONFIG = {
    "ORIGINAL_FOLDER": os.path.join(BASE_DIR, "files", "original"),
    "METADATA": os.path.join(BASE_DIR, "files", "original", "secciones.json"),
    "CLONE_EXAMPLES": os.path.join(BASE_DIR, "files", "clone_examples"),
    "EXAMPLES_JSON": os.path.join(BASE_DIR, "files", "clone_examples", "examples.json"),
    "OUTPUT_AUDIO": os.path.join(BASE_DIR, "files", "audios"),
    "PINOKIO_URL": "http://127.0.0.1:7860"
}

# Inicializar Pygame Mixer para reproducción de audio
pygame.mixer.init()

class AudioEngine:
    """Clase de utilidad para procesar y reproducir fragmentos de audio."""
    @staticmethod
    def play_fragment(audio_path, start_ms, end_ms):
        try:
            full_audio = AudioSegment.from_file(audio_path)
            extract = full_audio[start_ms:end_ms]
            
            # Exportar a buffer en memoria (WAV) para Pygame
            buffer = io.BytesIO()
            extract.export(buffer, format="wav")
            buffer.seek(0)
            
            pygame.mixer.music.load(buffer)
            pygame.mixer.music.play()
        except Exception as e:
            messagebox.showerror("Error de Audio", f"No se pudo reproducir: {e}")

class SegmentCard(ctk.CTkFrame):
    """Tarjeta individual para cada segmento de audio."""
    def __init__(self, master, segment_data, original_audio_path, save_callback, **kwargs):
        super().__init__(master, **kwargs)
        self.data = segment_data
        self.original_audio_path = original_audio_path
        self.save_callback = save_callback
        
        self.configure(fg_color="#2b2b2b", border_width=1, border_color="#3d3d3d")
        self.grid_columnconfigure(1, weight=1)

        # --- FILA 1: ID y Original ---
        self.lbl_id = ctk.CTkLabel(self, text=f"ID: {self.data['id']}", font=("Arial", 11, "bold"), text_color="#aaaaaa")
        self.lbl_id.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")
        
        self.lbl_orig = ctk.CTkLabel(self, text=self.data['original'], font=("Arial", 12, "italic"), wraplength=600, justify="left")
        self.lbl_orig.grid(row=0, column=1, columnspan=2, padx=10, pady=(5, 0), sticky="w")

        # --- FILA 2: Traducción Editable ---
        self.txt_translated = ctk.CTkTextbox(self, height=60, font=("Arial", 13))
        self.txt_translated.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        self.txt_translated.insert("1.0", self.data.get('translated', ''))

        # --- FILA 3: Controles de tiempo y tono ---
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(ctrl_frame, text="Inicio (ms):").pack(side="left", padx=2)
        self.ent_start = ctk.CTkEntry(ctrl_frame, width=70)
        self.ent_start.insert(0, str(self.data['start_ms']))
        self.ent_start.pack(side="left", padx=5)

        ctk.CTkLabel(ctrl_frame, text="Fin (ms):").pack(side="left", padx=2)
        self.ent_end = ctk.CTkEntry(ctrl_frame, width=70)
        self.ent_end.insert(0, str(self.data['end_ms']))
        self.ent_end.pack(side="left", padx=5)

        ctk.CTkLabel(ctrl_frame, text="Tono:").pack(side="left", padx=(15, 2))
        self.opt_tone = ctk.CTkOptionMenu(ctrl_frame, values=["Conversational", "Explanatory", "Effusive", "Serious"], width=130)
        self.opt_tone.set(self.data.get('tone', 'Conversational'))
        self.opt_tone.pack(side="left", padx=5)

        # --- FILA 4: Botones de Acción ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="ew")

        self.btn_play = ctk.CTkButton(btn_frame, text="▶ Reproducir Original", width=150, fg_color="#444444", hover_color="#555555",
                                      command=self._play_slice)
        self.btn_play.pack(side="left", padx=5)

        self.btn_save = ctk.CTkButton(btn_frame, text="💾 Guardar Cambios", width=150, fg_color="#1f538d",
                                      command=self._save_local_changes)
        self.btn_save.pack(side="left", padx=5)

    def _play_slice(self):
        try:
            start = int(self.ent_start.get())
            end = int(self.ent_end.get())
            AudioEngine.play_fragment(self.original_audio_path, start, end)
        except ValueError:
            messagebox.showwarning("Valor inválido", "El tiempo debe ser numérico (ms).")

    def _save_local_changes(self):
        # Actualizar diccionario en memoria
        self.data['translated'] = self.txt_translated.get("1.0", "end-1c")
        self.data['start_ms'] = int(self.ent_start.get())
        self.data['end_ms'] = int(self.ent_end.get())
        self.data['tone'] = self.opt_tone.get()
        
        if self.save_callback(self.data):
            self.configure(border_color="#28a745") # Feedback visual: verde al guardar
            self.after(1000, lambda: self.configure(border_color="#3d3d3d"))

    def set_status_processing(self):
        self.configure(border_color="#ffc107") # Amarillo

    def set_status_done(self):
        self.configure(border_color="#28a745", fg_color="#1b2e1b") # Verde oscuro

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Logic Imprint - Dubbing Manager")
        self.geometry("1000(800")
        ctk.set_appearance_mode("Dark")
        
        self.segments_data = []
        self.card_widgets = {}
        self.original_audio_file = self._find_original_audio()
        
        self._ensure_directories()
        self._setup_ui()
        self.load_data()

    def _ensure_directories(self):
        os.makedirs(PATH_CONFIG["OUTPUT_AUDIO"], exist_ok=True)

    def _find_original_audio(self):
        folder = PATH_CONFIG["ORIGINAL_FOLDER"]
        for f in os.listdir(folder):
            if f.startswith("original.") and f.endswith((".mp3", ".wav")):
                return os.path.join(folder, f)
        return None

    def _setup_ui(self):
        # Cabecera
        self.top_frame = ctk.CTkFrame(self, height=80, corner_radius=0)
        self.top_frame.pack(fill="x", side="top")
        
        self.lbl_title = ctk.CTkLabel(self.top_frame, text="Logic Imprint - Dubbing Manager", font=("Arial", 24, "bold"))
        self.lbl_title.pack(side="left", padx=20, pady=20)
        
        self.btn_run_all = ctk.CTkButton(self.top_frame, text="🚀 Solicitar Audios a Pinokio", 
                                         font=("Arial", 14, "bold"), fg_color="#28a745", hover_color="#218838",
                                         command=self.start_dubbing_process)
        self.btn_run_all.pack(side="right", padx=20, pady=20)

        # Cuerpo scrolleable
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Segmentos de Metadata")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def load_data(self):
        if not os.path.exists(PATH_CONFIG["METADATA"]):
            messagebox.showerror("Error", "No se encontró metadata.json")
            return

        with open(PATH_CONFIG["METADATA"], "r", encoding="utf-8") as f:
            self.segments_data = json.load(f)

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        for seg in self.segments_data:
            card = SegmentCard(self.scroll_frame, seg, self.original_audio_file, self.save_metadata_to_disk)
            card.pack(fill="x", padx=5, pady=5)
            self.card_widgets[seg['id']] = card

    def save_metadata_to_disk(self, updated_seg):
        # Actualizar la lista principal
        for i, seg in enumerate(self.segments_data):
            if seg['id'] == updated_seg['id']:
                self.segments_data[i] = updated_seg
                break
        
        try:
            with open(PATH_CONFIG["METADATA"], "w", encoding="utf-8") as f:
                json.dump(self.segments_data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar JSON: {e}")
            return False

    def start_dubbing_process(self):
        # Ejecutar en hilo separado
        threading.Thread(target=self._dubbing_worker, daemon=True).start()

    def _dubbing_worker(self):
        self.btn_run_all.configure(state="disabled", text="Procesando...")
        
        try:
            client = Client(PATH_CONFIG["PINOKIO_URL"])
            
            # Cargar ejemplos de clonación
            with open(PATH_CONFIG["EXAMPLES_JSON"], "r", encoding="utf-8") as f:
                examples = json.load(f)
            
            # Mapear tono -> texto_referencia
            tone_map = {ex['tono']: ex['transcripcion'] for ex in examples}

            for seg in self.segments_data:
                seg_id = seg['id']
                tone = seg.get('tone', 'Serious')
                
                # UI feedback
                self.after(0, lambda s=seg_id: self.card_widgets[s].set_status_processing())

                ref_audio_path = os.path.join(PATH_CONFIG["CLONE_EXAMPLES"], f"ref_{tone}.wav")
                ref_text = tone_map.get(tone, "Hello, this is a reference text.")

                # Llamada API
                result = client.predict(
                    ref_audio=handle_file(ref_audio_path),
                    ref_text=ref_text,
                    target_text=seg['translated'],
                    language="English",
                    use_xvector_only=False,
                    model_size="1.7B",
                    max_chunk_chars=200,
                    chunk_gap=0.0,
                    seed=-1,
                    api_name="/generate_voice_clone"
                )

                # Mover archivo
                temp_path = result[0]
                final_path = os.path.join(PATH_CONFIG["OUTPUT_AUDIO"], seg['filename'])
                shutil.move(temp_path, final_path)

                # UI feedback finalizado
                self.after(0, lambda s=seg_id: self.card_widgets[s].set_status_done())

            messagebox.showinfo("Proceso Completo", "Todos los audios han sido generados en la carpeta 'audios'.")
        
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: messagebox.showerror("Error en API", f"Falló la conexión o el proceso: {msg}"))
        finally:
            self.after(0, lambda: self.btn_run_all.configure(state="normal", text="🚀 Solicitar Audios a Pinokio"))

if __name__ == "__main__":
    app = App()
    app.mainloop()
