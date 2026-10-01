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
    def __init__(self, master, segment_data, original_audio_path, save_callback, delete_callback, request_callback, **kwargs):
        super().__init__(master, **kwargs)
        self.data = segment_data
        self.original_audio_path = original_audio_path
        self.save_callback = save_callback
        self.delete_callback = delete_callback
        self.request_callback = request_callback
        
        self.configure(fg_color="#2b2b2b", border_width=1, border_color="#3d3d3d")
        
        # Configurar las columnas de la tarjeta:
        # Columna 0: Para el ID (ancho fijo)
        # Columna 1: Para el contenido principal (texto, entradas, menú desplegable), esta columna se expandirá
        self.grid_columnconfigure(0, weight=0) # Columna para el ID, no se expande
        self.grid_columnconfigure(1, weight=1) # Columna para el contenido, se expande

        # --- FILA 1: ID y Original ---
        self.lbl_id = ctk.CTkLabel(self, text=f"ID: {self.data['id']}", font=("Arial", 11, "bold"), text_color="#aaaaaa")
        self.lbl_id.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="nw") # Alineado arriba-izquierda
        
        # Crear un sub-frame para el texto original y traducido para controlar su ancho
        text_content_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_content_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=5, sticky="nsew") # Ocupa la columna 1 y 2 filas
        text_content_frame.grid_columnconfigure(0, weight=1) # La columna interna se expande

        self.lbl_orig = ctk.CTkLabel(text_content_frame, text=self.data['original'], font=("Arial", 12, "italic"), wraplength=600, justify="left")
        self.lbl_orig.grid(row=0, column=0, sticky="ew") # Se expande dentro de text_content_frame
        
        self.txt_translated = ctk.CTkTextbox(text_content_frame, height=60, font=("Arial", 13))
        self.txt_translated.grid(row=1, column=0, pady=(5,0), sticky="ew") # Se expande dentro de text_content_frame
        self.txt_translated.insert("1.0", self.data.get('translated', ''))

        # --- FILA 3: Controles de tiempo y tono ---
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent") # Este frame ahora abarca ambas columnas principales
        ctrl_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

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
        btn_frame = ctk.CTkFrame(self, fg_color="transparent") # Este frame ahora abarca ambas columnas principales
        btn_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        self.btn_play = ctk.CTkButton(btn_frame, text="▶ Reproducir Original", width=150, fg_color="#444444", hover_color="#555555",
                                      command=self._play_slice)
        self.btn_play.pack(side="left", padx=5)

        self.btn_save = ctk.CTkButton(btn_frame, text="💾 Guardar Cambios", width=150, fg_color="#1f538d",
                                      command=self._save_local_changes)
        self.btn_save.pack(side="left", padx=5)

        self.btn_request = ctk.CTkButton(btn_frame, text="✨ Generar este", width=120, fg_color="#7b1fa2", hover_color="#4a148c",
                                         command=lambda: self.request_callback(self.data))
        self.btn_request.pack(side="left", padx=5)

        self.btn_play_gen = ctk.CTkButton(btn_frame, text="🎧 Oír Generado", width=120, fg_color="#607d8b", hover_color="#455a64",
                                          command=self._play_generated)
        self.btn_play_gen.pack(side="left", padx=5)

        self.btn_delete = ctk.CTkButton(btn_frame, text="🗑 Eliminar", width=100, fg_color="#a83232", hover_color="#822727",
                                        command=lambda: self.delete_callback(self.data))
        self.btn_delete.pack(side="right", padx=5)

        self.update_generated_status()

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

    def update_generated_status(self):
        path = os.path.join(PATH_CONFIG["OUTPUT_AUDIO"], self.data['filename'])
        if os.path.exists(path):
            self.btn_play_gen.configure(state="normal", fg_color="#2e7d32")
        else:
            self.btn_play_gen.configure(state="disabled", fg_color="#455a64")

    def _play_generated(self):
        path = os.path.join(PATH_CONFIG["OUTPUT_AUDIO"], self.data['filename'])
        if os.path.exists(path):
            try:
                # Leer archivo en memoria para evitar bloquear el archivo en disco (Windows)
                with open(path, "rb") as f:
                    audio_data = io.BytesIO(f.read())
                pygame.mixer.music.load(audio_data)
                pygame.mixer.music.play()
                self._current_buf = audio_data # Mantener referencia para evitar GC
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo reproducir: {e}")

    def set_status_processing(self):
        self.configure(border_color="#ffc107") # Amarillo

    def set_status_done(self):
        self.configure(border_color="#28a745", fg_color="#1b2e1b") # Verde oscuro

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Logic Imprint - Dubbing Manager")
        self.geometry("1000x800") # Corregido de "1000(800" a "1000x800"
        ctk.set_appearance_mode("Dark")
        
        self.segments_data = []
        self.card_widgets = {}
        self.original_audio_file = self._find_original_audio()
        self.total_duration_ms = 0
        
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

        if self.original_audio_file:
            audio = AudioSegment.from_file(self.original_audio_file)
            self.total_duration_ms = len(audio)

        # Calcular tiempos iniciales y guardar
        self.recalculate_end_times()
        self.save_metadata_to_disk(None) 
        self.refresh_ui()

    def recalculate_end_times(self):
        """Calcula end_ms basado en el start_ms del siguiente segmento."""
        if not self.segments_data: return
        
        # Convertir posibles valores None (null en JSON) a 0 para permitir la ordenación
        for seg in self.segments_data:
            if seg.get('start_ms') is None:
                seg['start_ms'] = 0

        self.segments_data.sort(key=lambda x: x['start_ms'])
        for i in range(len(self.segments_data) - 1):
            self.segments_data[i]['end_ms'] = self.segments_data[i+1]['start_ms']
        
        if self.total_duration_ms > 0:
            self.segments_data[-1]['end_ms'] = self.total_duration_ms

    def refresh_ui(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        
        self.card_widgets.clear()
        for seg in self.segments_data:
            card = SegmentCard(self.scroll_frame, seg, self.original_audio_file, self.save_metadata_to_disk, self.delete_segment, self.request_single_segment)
            card.pack(fill="x", padx=5, pady=5)
            self.card_widgets[seg['id']] = card

    def save_metadata_to_disk(self, updated_seg=None):
        if updated_seg:
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

    def delete_segment(self, segment_to_delete):
        if messagebox.askyesno("Confirmar", f"¿Estás seguro de eliminar el segmento {segment_to_delete['id']}?"):
            self.segments_data = [s for s in self.segments_data if s['id'] != segment_to_delete['id']]
            self.recalculate_end_times()
            self.save_metadata_to_disk()
            self.refresh_ui()

    def start_dubbing_process(self):
        # Ejecutar en hilo separado
        threading.Thread(target=self._dubbing_worker, daemon=True).start()

    def request_single_segment(self, seg_data):
        threading.Thread(target=self._single_dubbing_worker, args=(seg_data,), daemon=True).start()

    def _get_api_resources(self):
        client = Client(PATH_CONFIG["PINOKIO_URL"])
        with open(PATH_CONFIG["EXAMPLES_JSON"], "r", encoding="utf-8") as f:
            examples = json.load(f)
        tone_map = {ex['tono']: ex['transcripcion'] for ex in examples}
        return client, tone_map

    def _run_segment_generation(self, seg, client, tone_map):
        seg_id = seg['id']
        tone = seg.get('tone', 'Serious')
        self.after(0, lambda: self.card_widgets[seg_id].set_status_processing())

        ref_audio_path = os.path.join(PATH_CONFIG["CLONE_EXAMPLES"], f"ref_{tone}.wav")
        ref_text = tone_map.get(tone, "Hello, this is a reference text.")

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

        # Detener el mixer y liberar archivos para evitar el error de acceso denegado en Windows
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except AttributeError:
            pygame.mixer.music.load(io.BytesIO()) # Fallback para liberar el lock en versiones antiguas

        temp_path = result[0]
        final_path = os.path.join(PATH_CONFIG["OUTPUT_AUDIO"], seg['filename'])
        shutil.move(temp_path, final_path)

        self.after(0, lambda: self.card_widgets[seg_id].set_status_done())
        self.after(0, lambda: self.card_widgets[seg_id].update_generated_status())

    def _dubbing_worker(self):
        self.btn_run_all.configure(state="disabled", text="Procesando...")
        try:
            client, tone_map = self._get_api_resources()
            for seg in self.segments_data:
                self._run_segment_generation(seg, client, tone_map)
            messagebox.showinfo("Proceso Completo", "Todos los audios han sido generados en la carpeta 'audios'.")
        except Exception as e:
            self.after(0, lambda msg=str(e): messagebox.showerror("Error en API", f"Falló el proceso: {msg}"))
        finally:
            self.after(0, lambda: self.btn_run_all.configure(state="normal", text="🚀 Solicitar Audios a Pinokio"))

    def _single_dubbing_worker(self, seg):
        try:
            client, tone_map = self._get_api_resources()
            self._run_segment_generation(seg, client, tone_map)
        except Exception as e:
            self.after(0, lambda msg=str(e): messagebox.showerror("Error", f"No se pudo generar el audio: {msg}"))

if __name__ == "__main__":
    app = App()
    app.mainloop()
