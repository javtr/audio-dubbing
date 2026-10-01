import os
import sys
import json
import time
import math
import shutil
import io
import queue
import threading
import subprocess
import gc
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Parche de seguridad para Python 3.12+: evitar que el Garbage Collector en hilos secundarios dispare RuntimeError
_orig_var_del = tk.Variable.__del__
def _safe_var_del(self):
    if threading.current_thread() is threading.main_thread():
        try:
            _orig_var_del(self)
        except Exception:
            pass
tk.Variable.__del__ = _safe_var_del

_orig_img_del = tk.Image.__del__
def _safe_img_del(self):
    if threading.current_thread() is threading.main_thread():
        try:
            _orig_img_del(self)
        except Exception:
            pass
tk.Image.__del__ = _safe_img_del
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pygame
from pydub import AudioSegment


from core.project_manager import ProjectManager
from core.whisper_aligner import WhisperAligner
from core.pinokio_client import PinokioClient
from core.audio_processor import AudioProcessor

# Inicializar motor de audio Pygame
pygame.mixer.init()

class NewProjectDialog(ctk.CTkToplevel):
    """Diálogo modal para crear un nuevo proyecto."""
    def __init__(self, parent, on_create_callback):
        super().__init__(parent)
        self.title("Crear Nuevo Proyecto")
        self.geometry("520x260")
        self.resizable(False, False)
        self.on_create_callback = on_create_callback
        self.selected_file = None

        self.transient(parent)
        self.grab_set()

        # Nombre del proyecto
        lbl_name = ctk.CTkLabel(self, text="Nombre del Proyecto:", font=("Arial", 13, "bold"))
        lbl_name.pack(anchor="w", padx=25, pady=(20, 5))

        self.ent_name = ctk.CTkEntry(self, placeholder_text="Ej: Tutorial_Volume_Profile", width=470)
        self.ent_name.pack(padx=25, pady=(0, 15))

        # Archivo multimedia (Video o Audio)
        lbl_file = ctk.CTkLabel(self, text="Video (.mp4) o Audio de Entrada:", font=("Arial", 13, "bold"))
        lbl_file.pack(anchor="w", padx=25, pady=(0, 5))

        file_frame = ctk.CTkFrame(self, fg_color="transparent")
        file_frame.pack(fill="x", padx=25, pady=(0, 20))

        self.lbl_selected = ctk.CTkLabel(file_frame, text="Ningún archivo seleccionado", text_color="#aaaaaa", anchor="w")
        self.lbl_selected.pack(side="left", fill="x", expand=True)

        btn_browse = ctk.CTkButton(file_frame, text="Examinar...", width=110, command=self._browse_file)
        btn_browse.pack(side="right")

        # Botones inferiores
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=25, pady=(0, 15))

        btn_cancel = ctk.CTkButton(btn_frame, text="Cancelar", fg_color="#555555", hover_color="#666666", width=120, command=self.destroy)
        btn_cancel.pack(side="left")

        self.btn_create = ctk.CTkButton(btn_frame, text="Crear Proyecto", fg_color="#28a745", hover_color="#218838", width=160, command=self._submit)
        self.btn_create.pack(side="right")

    def _browse_file(self):
        f = filedialog.askopenfilename(
            title="Seleccionar Video o Audio",
            filetypes=[
                ("Archivos Multimedia", "*.mp4 *.mkv *.mov *.avi *.webm *.wav *.mp3 *.m4a *.flac"),
                ("Videos", "*.mp4 *.mkv *.mov *.avi *.webm"),
                ("Audios", "*.wav *.mp3 *.m4a *.flac")
            ]
        )
        if f:
            self.selected_file = f
            self.lbl_selected.configure(text=os.path.basename(f), text_color="#ffffff")
            if not self.ent_name.get().strip():
                base = os.path.splitext(os.path.basename(f))[0]
                self.ent_name.insert(0, base)

    def _submit(self):
        name = self.ent_name.get().strip()
        if not name:
            messagebox.showwarning("Atención", "Por favor ingresa un nombre para el proyecto.")
            return

        self.btn_create.configure(state="disabled", text="Creando...")
        self.on_create_callback(name, self.selected_file)
        self.destroy()


class SegmentCard(ctk.CTkFrame):
    """Tarjeta individual para editar y doblar cada segmento en la Pestaña 2."""
    def __init__(self, master, segment_data, audio_path, audios_dir, save_callback, delete_callback, request_callback, **kwargs):
        super().__init__(master, **kwargs)
        self.data = segment_data
        self.original_audio_path = audio_path
        self.audios_dir = audios_dir
        self.save_callback = save_callback
        self.delete_callback = delete_callback
        self.request_callback = request_callback

        self.configure(fg_color="#2b2b2b", border_width=1, border_color="#3d3d3d")
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ID
        self.lbl_id = ctk.CTkLabel(self, text=f"ID: {self.data.get('id', 'seg')}", font=("Arial", 11, "bold"), text_color="#aaaaaa")
        self.lbl_id.grid(row=0, column=0, padx=10, pady=(8, 0), sticky="nw")

        # Contenido de texto
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=5, sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)

        self.lbl_orig = ctk.CTkLabel(text_frame, text=self.data.get('original', ''), font=("Arial", 12, "italic"), wraplength=650, justify="left")
        self.lbl_orig.grid(row=0, column=0, sticky="ew")

        self.txt_translated = ctk.CTkTextbox(text_frame, height=55, font=("Arial", 13))
        self.txt_translated.grid(row=1, column=0, pady=(5, 0), sticky="ew")
        self.txt_translated.insert("1.0", self.data.get('translated', ''))

        # Indicador de densidad y ritmo rítmico (isocronía)
        self.lbl_density = ctk.CTkLabel(text_frame, text="", font=("Arial", 11, "bold"), anchor="w", justify="left")
        self.lbl_density.grid(row=2, column=0, pady=(3, 0), sticky="w")

        # Controles de tiempo y tono
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(ctrl_frame, text="Inicio (ms):").pack(side="left", padx=2)
        self.ent_start = ctk.CTkEntry(ctrl_frame, width=75)
        self.ent_start.insert(0, str(self.data.get('start_ms', 0)))
        self.ent_start.pack(side="left", padx=5)

        ctk.CTkLabel(ctrl_frame, text="Fin (ms):").pack(side="left", padx=2)
        self.ent_end = ctk.CTkEntry(ctrl_frame, width=75)
        self.ent_end.insert(0, str(self.data.get('end_ms', 0)))
        self.ent_end.pack(side="left", padx=5)

        ctk.CTkLabel(ctrl_frame, text="Tono:").pack(side="left", padx=(15, 2))
        self.opt_tone = ctk.CTkOptionMenu(ctrl_frame, values=["Conversational", "Explanatory", "Effusive", "Serious"], width=140)
        self.opt_tone.set(self.data.get('tone', 'Conversational'))
        self.opt_tone.pack(side="left", padx=5)

        # Eventos para cálculo de densidad en tiempo real
        self.txt_translated.bind("<KeyRelease>", lambda e: self.update_density_metrics())
        self.ent_start.bind("<KeyRelease>", lambda e: self.update_density_metrics())
        self.ent_end.bind("<KeyRelease>", lambda e: self.update_density_metrics())

        # Botones de acción
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        self.btn_play_orig = ctk.CTkButton(btn_frame, text="▶ Original", width=110, fg_color="#444444", hover_color="#555555", command=self._play_slice)
        self.btn_play_orig.pack(side="left", padx=5)

        self.btn_save = ctk.CTkButton(btn_frame, text="💾 Guardar", width=110, fg_color="#1f538d", command=self._save_changes)
        self.btn_save.pack(side="left", padx=5)

        self.btn_request = ctk.CTkButton(btn_frame, text="✨ Generar este", width=125, fg_color="#7b1fa2", hover_color="#4a148c", command=lambda: self.request_callback(self.data))
        self.btn_request.pack(side="left", padx=5)

        self.btn_play_gen = ctk.CTkButton(btn_frame, text="🎧 Oír Doblado", width=125, fg_color="#607d8b", hover_color="#455a64", command=self._play_generated)
        self.btn_play_gen.pack(side="left", padx=5)

        self.btn_delete = ctk.CTkButton(btn_frame, text="🗑 Eliminar", width=95, fg_color="#a83232", hover_color="#822727", command=lambda: self.delete_callback(self.data))
        self.btn_delete.pack(side="right", padx=5)

        self.update_density_metrics()
        self.update_status()

    def update_density_metrics(self):
        try:
            start = int(self.ent_start.get())
            end = int(self.ent_end.get())
            duration_sec = (end - start) / 1000.0
        except ValueError:
            self.lbl_density.configure(text="⚠️ Tiempos inválidos", text_color="#e57373")
            return

        orig_text = self.data.get('original', '').strip()
        orig_words = len(orig_text.split()) if orig_text else 0

        trans_text = self.txt_translated.get("1.0", "end-1c").strip()
        trans_words = len(trans_text.split()) if trans_text else 0

        if duration_sec <= 0:
            self.lbl_density.configure(text="⚠️ Duración inválida (<= 0s)", text_color="#e57373")
            return

        if trans_words == 0:
            self.lbl_density.configure(text=f"[{duration_sec:.1f}s] Original: {orig_words} pal. | ⚠️ Sin traducción", text_color="#aaaaaa")
            return

        wps = trans_words / duration_sec
        wpm = int(wps * 60)

        # Rango conversacional estándar en inglés: ~2.0 a 2.8 palabras/segundo (120-170 WPM)
        if wps < 1.7:
            info = f"[{duration_sec:.1f}s] {trans_words} pal. ({wps:.1f} pal/s - {wpm} WPM) | ⚠️ Corta (ES: {orig_words} pal.) - Sobrará silencio"
            color = "#ffb74d"
        elif wps > 3.2:
            info = f"[{duration_sec:.1f}s] {trans_words} pal. ({wps:.1f} pal/s - {wpm} WPM) | ⚠️ Larga (ES: {orig_words} pal.) - Deberá acelerarse"
            color = "#e57373"
        else:
            info = f"[{duration_sec:.1f}s] {trans_words} pal. ({wps:.1f} pal/s - {wpm} WPM) | ✅ Ritmo equilibrado (ES: {orig_words} pal.)"
            color = "#81c784"

        self.lbl_density.configure(text=info, text_color=color)

    def _play_slice(self):
        try:
            start = int(self.ent_start.get())
            end = int(self.ent_end.get())
            if not self.original_audio_path or not os.path.exists(self.original_audio_path):
                return
            audio = AudioSegment.from_file(self.original_audio_path)
            slice_audio = audio[start:end]
            buf = io.BytesIO()
            slice_audio.export(buf, format="wav")
            buf.seek(0)
            pygame.mixer.music.load(buf)
            pygame.mixer.music.play()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo reproducir fragmento: {e}")

    def _play_generated(self):
        path = os.path.join(self.audios_dir, self.data.get('filename', ''))
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    buf = io.BytesIO(f.read())
                pygame.mixer.music.load(buf)
                pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo reproducir: {e}")

    def _save_changes(self):
        try:
            self.data['translated'] = self.txt_translated.get("1.0", "end-1c").strip()
            self.data['start_ms'] = int(self.ent_start.get())
            self.data['end_ms'] = int(self.ent_end.get())
            self.data['tone'] = self.opt_tone.get()
            self.save_callback(self.data)
            self.update_density_metrics()
            self.configure(border_color="#28a745")
            self.after(1000, lambda: self.configure(border_color="#3d3d3d"))
        except ValueError:
            messagebox.showwarning("Atención", "Los tiempos deben ser números enteros en milisegundos.")

    def update_status(self):
        filename = self.data.get('filename', '')
        path = os.path.join(self.audios_dir, filename)
        if os.path.exists(path):
            self.btn_play_gen.configure(state="normal", fg_color="#2e7d32")
        else:
            self.btn_play_gen.configure(state="disabled", fg_color="#455a64")

    def set_processing(self):
        self.configure(border_color="#ffc107")

    def set_done(self):
        self.configure(border_color="#28a745", fg_color="#1b2e1b")
        self.update_status()


class AudioDubbingStudio(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Logic Imprint - Audio Dubbing Studio")
        self.geometry("1100x820")
        self.minsize(950, 700)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Módulos Core
        self.pm = ProjectManager()
        self.aligner = WhisperAligner()
        self.pinokio = PinokioClient()
        self.processor = None

        # Variables de estado
        self.current_project = None
        self.project_paths = {}
        self.segments_data = []
        self.pinokio_connected = False

        # Variables de reproducción y mezcla (Pestaña 3)
        self.mute_original = False
        self.mute_dubbed = False
        self.playing_process = None
        self.playing_id = None
        self.is_dragging = False
        self.total_duration_ms = 1000
        self.play_start_sys_time = 0
        self.play_start_offset = 0
        self.segment_rows = {}

        # Cabezal de reproducción sobre las ondas y franjas de texto (Playhead)
        self.orig_canvas = None
        self.orig_cursor = None
        self.orig_cursor_text = None
        self.orig_ax = None
        self.orig_ax_text = None
        self.dub_canvas = None
        self.dub_cursor = None
        self.dub_cursor_text = None
        self.dub_ax = None
        self.dub_ax_text = None
        self.lbl_orig_hover = None
        self.lbl_dub_hover = None

        # Variables de manipulación interactiva de segmentos (Timeline Drag & Stretch)
        self.drag_mode = None          # "MOVE", "RESIZE" o "SEEK"
        self.drag_segment = None       # Diccionario del segmento activo
        self.drag_start_x = 0.0        # Posición inicial en ms al hacer clic
        self.orig_seg_start = 0        # start_ms antes de arrastrar
        self.orig_seg_end = 0          # end_ms antes de arrastrar
        self.orig_clip_raw_duration = 0  # Duración del audio sin estirar
        self.ghost_patch = None        # Patch visual de previsualización
        self.drag_has_moved = False    # Para distinguir clic simple de arrastre

        # Herramientas de edición de clips (Cuchilla / Razor y Selección)
        self.active_tool = "SELECT"     # "SELECT" o "RAZOR"
        self.selected_segment_id = None # ID del segmento seleccionado
        self.razor_guide_line = None    # Línea vertical roja guía de corte
        self.btn_tool_select = None
        self.btn_tool_razor = None
        self.btn_split_playhead = None
        self.btn_delete_seg = None

        # Atajos de teclado para edición
        self.bind("<Delete>", self._on_key_delete)
        self.bind("<BackSpace>", self._on_key_delete)
        self.bind("<c>", self._on_key_shortcut)
        self.bind("<C>", self._on_key_shortcut)
        self.bind("<v>", self._on_key_shortcut)
        self.bind("<V>", self._on_key_shortcut)

        # Cola para comunicación thread-safe entre hilos secundarios y la interfaz gráfica
        self._gui_queue = queue.Queue()
        self._poll_gui_queue()

        self._build_top_bar()
        self._build_tabs()
        self._check_pinokio_status_async()
        self._load_initial_project()

    def run_on_ui_thread(self, callback):
        """Encola una función para ejecutarse de forma segura en el hilo principal de Tkinter."""
        self._gui_queue.put(callback)

    def _poll_gui_queue(self):
        """Revisa periódicamente la cola de la interfaz y ejecuta callbacks en el hilo principal."""
        try:
            while True:
                task = self._gui_queue.get_nowait()
                try:
                    task()
                except Exception as e:
                    print(f"[Error UI Thread] {e}")
        except queue.Empty:
            pass
        finally:
            self.after(35, self._poll_gui_queue)

    # ==========================================================
    # 1. BARRA SUPERIOR: PROYECTOS Y ESTADO DE PINOKIO
    # ==========================================================
    def _build_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, height=65, corner_radius=0, fg_color="#1e1e1e")
        self.top_bar.pack(fill="x", side="top")

        # Título
        lbl_app = ctk.CTkLabel(self.top_bar, text="Audio Dubbing Studio", font=("Arial", 18, "bold"), text_color="#3B8ED0")
        lbl_app.pack(side="left", padx=(20, 15), pady=15)

        # Selector de Proyecto
        ctk.CTkLabel(self.top_bar, text="Proyecto:", font=("Arial", 12)).pack(side="left", padx=(10, 5))
        self.opt_project = ctk.CTkOptionMenu(self.top_bar, values=["(Sin proyectos)"], width=220, command=self._on_project_changed)
        self.opt_project.pack(side="left", padx=5)

        btn_new_proj = ctk.CTkButton(self.top_bar, text="➕ Nuevo", width=85, fg_color="#28a745", hover_color="#218838", command=self._show_new_project_dialog)
        btn_new_proj.pack(side="left", padx=5)

        # Estado de Pinokio
        pinokio_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        pinokio_frame.pack(side="right", padx=20)

        self.lbl_pinokio = ctk.CTkLabel(pinokio_frame, text="● Verificando Pinokio...", text_color="#aaaaaa", font=("Arial", 12))
        self.lbl_pinokio.pack(side="left", padx=(0, 8))

        btn_check_pinokio = ctk.CTkButton(pinokio_frame, text="🔄", width=32, height=28, fg_color="#333333", command=self._check_pinokio_status_async)
        btn_check_pinokio.pack(side="left")

    def _check_pinokio_status_async(self):
        def _check():
            online = self.pinokio.check_connection()
            self.pinokio_connected = online
            self.run_on_ui_thread(lambda: self._update_pinokio_ui(online))
        threading.Thread(target=_check, daemon=True).start()

    def _update_pinokio_ui(self, online):
        if online:
            self.lbl_pinokio.configure(text="● Pinokio Online", text_color="#28a745")
        else:
            self.lbl_pinokio.configure(text="● Pinokio Offline (127.0.0.1:7860)", text_color="#e57373")

    def _show_new_project_dialog(self):
        NewProjectDialog(self, self._create_new_project)

    def _create_new_project(self, name, source_file):
        try:
            safe_name, paths = self.pm.create_project(name, source_file)
            self._refresh_project_list(select_project=safe_name)
            messagebox.showinfo("Éxito", f"Proyecto '{safe_name}' creado correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear el proyecto: {e}")

    def _refresh_project_list(self, select_project=None):
        projects = self.pm.list_projects()
        if not projects:
            self.opt_project.configure(values=["(Sin proyectos)"])
            self.opt_project.set("(Sin proyectos)")
            return

        self.opt_project.configure(values=projects)
        target = select_project if select_project in projects else projects[0]
        self.opt_project.set(target)
        self._on_project_changed(target)

    def _load_initial_project(self):
        projects = self.pm.list_projects()
        if projects:
            self._refresh_project_list(projects[0])

    def _on_project_changed(self, project_name):
        if project_name == "(Sin proyectos)":
            return
        self.current_project = project_name
        self.project_paths = self.pm.get_project_paths(project_name)
        self.segments_data = self.pm.load_project_metadata(project_name)

        # Asegurar anclas fijas originales inmutables
        for seg in self.segments_data:
            if "orig_start_ms" not in seg:
                seg["orig_start_ms"] = seg.get("start_ms", 0)
            if "orig_end_ms" not in seg:
                seg["orig_end_ms"] = seg.get("end_ms", 0)

        # Inicializar AudioProcessor
        if self.project_paths.get("audio_file"):

            self.processor = AudioProcessor(
                self.project_paths["audio_file"],
                self.project_paths["audios_dir"],
                self.segments_data
            )
        else:
            self.processor = None

        self._refresh_tab1()
        self._refresh_tab2()
        self._refresh_tab3()

    # ==========================================================
    # 2. SISTEMA DE PESTAÑAS
    # ==========================================================
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        self.tab1 = self.tabview.add("1. Guion y Tiempos")
        self.tab2 = self.tabview.add("2. Doblaje (Pinokio)")
        self.tab3 = self.tabview.add("3. Estudio y Mezcla")

        self._build_tab1_ui()
        self._build_tab2_ui()
        self._build_tab3_ui()

    # ----------------------------------------------------------
    # PESTAÑA 1: TRANSCRIPCIÓN, PROMPT GEMINI Y SINCRONIZACIÓN
    # ----------------------------------------------------------
    def _build_tab1_ui(self):
        self.tab1.grid_columnconfigure(0, weight=1)
        self.tab1.grid_columnconfigure(1, weight=1)
        self.tab1.grid_rowconfigure(1, weight=1)

        # Panel Izquierdo: Transcripción y Asistente Gemini
        left_frame = ctk.CTkFrame(self.tab1)
        left_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")
        left_frame.grid_rowconfigure(2, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left_frame, text="Paso 1A: Transcripción y Prompt para Gemini", font=("Arial", 15, "bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        
        btn_bar = ctk.CTkFrame(left_frame, fg_color="transparent")
        btn_bar.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        self.btn_transcribe = ctk.CTkButton(btn_bar, text="🎙️ Transcribir Audio", command=self._start_transcribe_thread)
        self.btn_transcribe.pack(side="left", padx=(0, 5))

        self.btn_copy_prompt = ctk.CTkButton(btn_bar, text="📋 Copiar Prompt para Gemini", fg_color="#7b1fa2", hover_color="#4a148c", command=self._copy_gemini_prompt)
        self.btn_copy_prompt.pack(side="left", padx=5)

        self.txt_transcript = ctk.CTkTextbox(left_frame, font=("Arial", 12))
        self.txt_transcript.grid(row=2, column=0, padx=15, pady=10, sticky="nsew")

        self.lbl_t1_status = ctk.CTkLabel(left_frame, text="Listo.", text_color="#aaaaaa", font=("Arial", 11))
        self.lbl_t1_status.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="w")

        # Panel Derecho: Pegar JSON y Sincronización Whisper
        right_frame = ctk.CTkFrame(self.tab1)
        right_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right_frame, text="Paso 1B: JSON de Gemini y Tiempos", font=("Arial", 15, "bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        json_btn_bar = ctk.CTkFrame(right_frame, fg_color="transparent")
        json_btn_bar.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        btn_save_json = ctk.CTkButton(json_btn_bar, text="💾 Guardar JSON", width=120, command=self._save_raw_json)
        btn_save_json.pack(side="left", padx=(0, 5))

        self.btn_align = ctk.CTkButton(json_btn_bar, text="⏱️ Sincronizar Tiempos (Whisper)", fg_color="#28a745", hover_color="#218838", command=self._start_align_thread)
        self.btn_align.pack(side="left", padx=5)

        self.txt_json = ctk.CTkTextbox(right_frame, font=("Consolas", 12))
        self.txt_json.grid(row=2, column=0, padx=15, pady=10, sticky="nsew")

        self.lbl_t1_align_status = ctk.CTkLabel(right_frame, text="Pega aquí el JSON devuelto por Gemini.", text_color="#aaaaaa", font=("Arial", 11))
        self.lbl_t1_align_status.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="w")

    def _refresh_tab1(self):
        # Cargar JSON actual del proyecto en la caja de texto
        if self.segments_data:
            formatted = json.dumps(self.segments_data, indent=2, ensure_ascii=False)
            self.txt_json.delete("1.0", "end")
            self.txt_json.insert("1.0", formatted)
            self.lbl_t1_align_status.configure(text=f"{len(self.segments_data)} segmentos cargados en secciones.json", text_color="#28a745")
        else:
            self.txt_json.delete("1.0", "end")
            self.lbl_t1_align_status.configure(text="Pega aquí el JSON devuelto por Gemini.", text_color="#aaaaaa")

    def _start_transcribe_thread(self):
        if not self.project_paths.get("audio_file"):
            messagebox.showwarning("Atención", "El proyecto actual no tiene un archivo de audio válido.")
            return

        self.btn_transcribe.configure(state="disabled", text="Transcribiendo...")
        self.lbl_t1_status.configure(text="Cargando modelo Whisper...", text_color="#ffc107")

        def _worker():
            try:
                audio = self.project_paths["audio_file"]
                text = self.aligner.transcribe_to_plain_text(
                    audio, 
                    lambda s: self.run_on_ui_thread(lambda: self.lbl_t1_status.configure(text=s))
                )
                self.run_on_ui_thread(lambda: self._on_transcribe_success(text))
            except Exception as e:
                self.run_on_ui_thread(lambda: self._on_transcribe_error(str(e)))

        gc.collect()
        threading.Thread(target=_worker, daemon=True).start()

    def _on_transcribe_success(self, text):
        self.btn_transcribe.configure(state="normal", text="🎙️ Transcribir Audio")
        self.txt_transcript.delete("1.0", "end")
        self.txt_transcript.insert("1.0", text)
        self.lbl_t1_status.configure(text="¡Transcripción completada con éxito!", text_color="#28a745")

    def _on_transcribe_error(self, err):
        self.btn_transcribe.configure(state="normal", text="🎙️ Transcribir Audio")
        self.lbl_t1_status.configure(text=f"Error: {err}", text_color="#e57373")
        messagebox.showerror("Error de Transcripción", err)

    def _copy_gemini_prompt(self):
        content = self.txt_transcript.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showwarning("Atención", "Primero transcribe el audio o escribe el texto en el cuadro izquierdo.")
            return

        prompt = self.aligner.generate_gemini_prompt(content)
        self.clipboard_clear()
        self.clipboard_append(prompt)
        self.lbl_t1_status.configure(text="¡Prompt copiado al portapapeles! Pégalo en Gemini Web.", text_color="#28a745")
        messagebox.showinfo("Copiado", "El prompt formateado fue copiado al portapapeles.\nPégalo en Gemini Web y copia el JSON resultante.")

    def _save_raw_json(self):
        raw = self.txt_json.get("1.0", "end-1c").strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("El JSON debe ser una lista de segmentos [ { ... }, { ... } ]")
            self.segments_data = data
            self.pm.save_project_metadata(self.current_project, data)
            if self.processor:
                self.processor.metadata = data
                self.processor.recalculate_end_times()
            self._refresh_tab2()
            self._refresh_tab3()
            messagebox.showinfo("Guardado", f"Se guardaron {len(data)} segmentos en el proyecto.")
        except Exception as e:
            messagebox.showerror("Error en JSON", f"El formato JSON no es válido:\n{e}")

    def _start_align_thread(self):
        raw = self.txt_json.get("1.0", "end-1c").strip()
        if not raw:
            messagebox.showwarning("Atención", "Pega primero el JSON generado por Gemini en la caja de texto.")
            return

        try:
            data = json.loads(raw)
            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("La lista JSON está vacía.")
        except Exception as e:
            messagebox.showerror("Error", f"JSON inválido: {e}")
            return

        audio = self.project_paths.get("audio_file")
        if not audio or not os.path.exists(audio):
            messagebox.showerror("Error", "No se encontró el audio original del proyecto.")
            return

        self.btn_align.configure(state="disabled", text="Sincronizando...")
        self.lbl_t1_align_status.configure(text="Iniciando alineación por palabras con Whisper...", text_color="#ffc107")

        def _worker():
            try:
                aligned_data, duration_ms = self.aligner.align_timestamps(
                    audio, 
                    data, 
                    lambda s: self.run_on_ui_thread(lambda: self.lbl_t1_align_status.configure(text=s))
                )
                self.run_on_ui_thread(lambda: self._on_align_success(aligned_data, duration_ms))
            except Exception as e:
                self.run_on_ui_thread(lambda: self._on_align_error(str(e)))

        gc.collect()
        threading.Thread(target=_worker, daemon=True).start()

    def _on_align_success(self, aligned_data, duration_ms):
        self.btn_align.configure(state="normal", text="⏱️ Sincronizar Tiempos (Whisper)")
        self.segments_data = aligned_data
        self.pm.save_project_metadata(self.current_project, aligned_data)
        if self.processor:
            self.processor.metadata = aligned_data
            self.processor.recalculate_end_times()
        self._refresh_tab1()
        self._refresh_tab2()
        self._refresh_tab3()
        messagebox.showinfo("Éxito", f"¡Tiempos sincronizados! {len(aligned_data)} segmentos alineados ({duration_ms} ms analizados).")

    def _on_align_error(self, err):
        self.btn_align.configure(state="normal", text="⏱️ Sincronizar Tiempos (Whisper)")
        self.lbl_t1_align_status.configure(text=f"Error en alineación: {err}", text_color="#e57373")
        messagebox.showerror("Error de Alineación", err)

    # ----------------------------------------------------------
    # PESTAÑA 2: DOBLAJE CON PINOKIO
    # ----------------------------------------------------------
    def _build_tab2_ui(self):
        # Barra superior de acciones
        top_frame = ctk.CTkFrame(self.tab2, height=50, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=10)

        self.btn_run_all = ctk.CTkButton(top_frame, text="🚀 Solicitar Todos a Pinokio", font=("Arial", 14, "bold"), fg_color="#28a745", hover_color="#218838", command=self._start_dubbing_all)
        self.btn_run_all.pack(side="left", padx=5)

        btn_reload = ctk.CTkButton(top_frame, text="🔄 Recargar", width=100, command=self._refresh_tab2)
        btn_reload.pack(side="left", padx=5)

        self.lbl_t2_progress = ctk.CTkLabel(top_frame, text="", font=("Arial", 12), text_color="#aaaaaa")
        self.lbl_t2_progress.pack(side="left", padx=20)

        # Contenedor desplazable de tarjetas
        self.scroll_cards = ctk.CTkScrollableFrame(self.tab2, label_text="Segmentos a Doblar")
        self.scroll_cards.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.card_widgets = {}

    def _refresh_tab2(self):
        for w in self.scroll_cards.winfo_children():
            w.destroy()
        self.card_widgets.clear()

        if not self.segments_data:
            ctk.CTkLabel(self.scroll_cards, text="No hay segmentos cargados. Completa el Paso 1 primero.", text_color="#aaaaaa").pack(pady=40)
            return

        audio_file = self.project_paths.get("audio_file")
        audios_dir = self.project_paths.get("audios_dir")

        for seg in self.segments_data:
            card = SegmentCard(
                self.scroll_cards,
                seg,
                audio_file,
                audios_dir,
                self._on_segment_saved,
                self._on_segment_deleted,
                self._start_single_dubbing
            )
            card.pack(fill="x", padx=5, pady=5)
            self.card_widgets[seg['id']] = card

    def _on_segment_saved(self, updated_seg):
        for i, s in enumerate(self.segments_data):
            if s['id'] == updated_seg['id']:
                self.segments_data[i] = updated_seg
                break
        self.pm.save_project_metadata(self.current_project, self.segments_data)
        if self.processor:
            self.processor.metadata = self.segments_data
            self.processor.recalculate_end_times()

    def _on_segment_deleted(self, seg_to_delete):
        if messagebox.askyesno("Confirmar", f"¿Eliminar el segmento {seg_to_delete['id']}?"):
            self.segments_data = [s for s in self.segments_data if s['id'] != seg_to_delete['id']]
            self.pm.save_project_metadata(self.current_project, self.segments_data)
            self._refresh_tab2()
            self._refresh_tab3()

    def _start_single_dubbing(self, seg):
        if not self.pinokio.check_connection():
            messagebox.showerror("Pinokio Desconectado", "No se puede conectar a Pinokio en http://127.0.0.1:7860.\nAsegúrate de tener iniciada la app de CosyVoice en Pinokio.")
            return

        card = self.card_widgets.get(seg['id'])
        if card:
            card.set_processing()

        def _worker():
            try:
                self._generate_segment_voice(seg)
                self.run_on_ui_thread(lambda: card.set_done() if card else None)
            except Exception as e:
                self.run_on_ui_thread(lambda: messagebox.showerror("Error en Doblaje", f"Fallo al generar {seg['id']}: {e}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _start_dubbing_all(self):
        if not self.pinokio.check_connection():
            messagebox.showerror("Pinokio Desconectado", "No se puede conectar a Pinokio en http://127.0.0.1:7860.\nAsegúrate de tener iniciada la app de CosyVoice en Pinokio.")
            return

        if not self.segments_data:
            messagebox.showwarning("Atención", "No hay segmentos para doblar.")
            return

        self.btn_run_all.configure(state="disabled", text="Procesando...")

        def _worker():
            total = len(self.segments_data)
            for i, seg in enumerate(self.segments_data):
                card = self.card_widgets.get(seg['id'])
                if card:
                    self.run_on_ui_thread(card.set_processing)
                self.run_on_ui_thread(lambda idx=i+1: self.lbl_t2_progress.configure(text=f"Generando {idx} de {total}..."))
                try:
                    self._generate_segment_voice(seg)
                    if card:
                        self.run_on_ui_thread(card.set_done)
                except Exception as e:
                    print(f"[ERROR] Error generando segmento {seg['id']}: {e}")

            self.run_on_ui_thread(self._on_dubbing_all_finished)

        threading.Thread(target=_worker, daemon=True).start()

    def _generate_segment_voice(self, seg):
        tone = seg.get('tone', 'Conversational')
        examples = self.pm.get_examples_config()
        tone_map = {ex['tono']: ex['transcripcion'] for ex in examples}

        ref_audio_path = os.path.join(self.pm.assets_dir, f"ref_{tone}.wav")
        ref_text = tone_map.get(tone, "This is a reference text.")
        output_path = os.path.join(self.project_paths["audios_dir"], seg['filename'])

        # Detener reproducción antes de sobreescribir archivo
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        self.pinokio.generate_voice_clone(
            ref_audio_path=ref_audio_path,
            ref_text=ref_text,
            target_text=seg['translated'],
            output_path=output_path
        )

    def _on_dubbing_all_finished(self):
        self.btn_run_all.configure(state="normal", text="🚀 Solicitar Todos a Pinokio")
        self.lbl_t2_progress.configure(text="¡Todos los segmentos generados!", text_color="#28a745")
        self._refresh_tab3()
        messagebox.showinfo("Completado", "Se han generado todos los audios en la carpeta 'audios' del proyecto.")

    # ----------------------------------------------------------
    # PESTAÑA 3: ESTUDIO Y MEZCLA
    # ----------------------------------------------------------
    def _build_tab3_ui(self):
        self.tab3.grid_rowconfigure(0, weight=3)
        self.tab3.grid_rowconfigure(1, weight=2)
        self.tab3.grid_columnconfigure(0, weight=1)

        # --- ZONA SUPERIOR: FORMAS DE ONDA ---
        wave_frame = ctk.CTkFrame(self.tab3)
        wave_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        wave_frame.grid_columnconfigure(0, weight=1)
        wave_frame.grid_rowconfigure(0, weight=1)
        wave_frame.grid_rowconfigure(1, weight=1)

        # Pista Original
        orig_box = ctk.CTkFrame(wave_frame)
        orig_box.grid(row=0, column=0, sticky="nsew", padx=5, pady=3)
        orig_box.grid_columnconfigure(0, weight=1)
        orig_box.grid_rowconfigure(1, weight=1)

        orig_header = ctk.CTkFrame(orig_box, fg_color="transparent")
        orig_header.grid(row=0, column=0, sticky="ew", padx=8, pady=2)
        ctk.CTkLabel(orig_header, text="Pista Original", font=("Arial", 12, "bold")).pack(side="left")
        self.btn_mute_orig = ctk.CTkButton(orig_header, text="Mute", width=55, height=24, command=self._toggle_mute_orig)
        self.btn_mute_orig.pack(side="left", padx=10)
        self.slider_vol_orig = ctk.CTkSlider(orig_header, from_=0, to=2, width=120)
        self.slider_vol_orig.set(1.0)
        self.slider_vol_orig.pack(side="left", padx=5)

        self.lbl_orig_hover = ctk.CTkLabel(orig_header, text="", font=("Arial", 11, "italic"), text_color="#38bdf8", anchor="w")
        self.lbl_orig_hover.pack(side="left", padx=15, fill="x", expand=True)

        self.orig_canvas_frame = ctk.CTkFrame(orig_box)
        self.orig_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)

        # Pista Doblada
        dub_box = ctk.CTkFrame(wave_frame)
        dub_box.grid(row=1, column=0, sticky="nsew", padx=5, pady=3)
        dub_box.grid_columnconfigure(0, weight=1)
        dub_box.grid_rowconfigure(1, weight=1)

        dub_header = ctk.CTkFrame(dub_box, fg_color="transparent")
        dub_header.grid(row=0, column=0, sticky="ew", padx=8, pady=2)
        ctk.CTkLabel(dub_header, text="Pista Doblada", font=("Arial", 12, "bold")).pack(side="left")
        self.btn_mute_dub = ctk.CTkButton(dub_header, text="Mute", width=55, height=24, command=self._toggle_mute_dub)
        self.btn_mute_dub.pack(side="left", padx=8)
        self.slider_vol_dub = ctk.CTkSlider(dub_header, from_=0, to=2, width=100)
        self.slider_vol_dub.set(1.0)
        self.slider_vol_dub.pack(side="left", padx=4)

        # Barra de Herramientas de Edición (Mover, Cuchilla, Corte en Cabezal, Suprimir)
        self.btn_tool_select = ctk.CTkButton(
            dub_header, text="✋ Mover", width=68, height=24,
            fg_color="#1f6aa5", hover_color="#144870",
            command=lambda: self._set_tool_mode("SELECT")
        )
        self.btn_tool_select.pack(side="left", padx=(8, 2))

        self.btn_tool_razor = ctk.CTkButton(
            dub_header, text="✂️ Cuchilla", width=78, height=24,
            fg_color="#333333", hover_color="#c62828",
            command=lambda: self._set_tool_mode("RAZOR")
        )
        self.btn_tool_razor.pack(side="left", padx=2)

        self.btn_split_playhead = ctk.CTkButton(
            dub_header, text="✂️ En Cabezal", width=90, height=24,
            fg_color="#333333", hover_color="#e65100",
            command=self._split_at_playhead
        )
        self.btn_split_playhead.pack(side="left", padx=2)

        self.btn_delete_seg = ctk.CTkButton(
            dub_header, text="🗑️ Suprimir", width=78, height=24,
            fg_color="#2b2b2b", hover_color="#822727", state="disabled",
            command=self._delete_selected_segment
        )
        self.btn_delete_seg.pack(side="left", padx=2)

        self.btn_reset_dub = ctk.CTkButton(
            dub_header, text="↺ Resetear a Original", width=145, height=24,
            fg_color="#a83232", hover_color="#822727",
            command=self._reset_dubbed_positions
        )
        self.btn_reset_dub.pack(side="right", padx=10)

        self.lbl_dub_hover = ctk.CTkLabel(dub_header, text="", font=("Arial", 11, "italic"), text_color="#ffb74d", anchor="w")
        self.lbl_dub_hover.pack(side="left", padx=10, fill="x", expand=True)

        self.dub_canvas_frame = ctk.CTkFrame(dub_box)
        self.dub_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)

        # --- ZONA MEDIA: SEGMENTOS GRANULARES ---
        self.mid_scroll = ctk.CTkScrollableFrame(self.tab3, label_text="Ajuste Fino de Segmentos")
        self.mid_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # --- BARRA DE PROGRESO / SEEK ---
        seek_frame = ctk.CTkFrame(self.tab3)
        seek_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.seek_slider = ctk.CTkSlider(seek_frame, from_=0, to=100, command=self._on_seek_change)
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self.seek_slider.bind("<ButtonPress-1>", lambda e: setattr(self, 'is_dragging', True))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)

        self.lbl_time = ctk.CTkLabel(seek_frame, text="00:00 / 00:00", width=90)
        self.lbl_time.pack(side="right", padx=10)

        # --- ZONA INFERIOR: BOTONES GLOBALES Y EXPORTACIÓN ---
        bot_frame = ctk.CTkFrame(self.tab3)
        bot_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=8)

        self.btn_play_mix = ctk.CTkButton(bot_frame, text="▶ Reproducir Mezcla", font=("Arial", 14, "bold"), fg_color="#007bff", hover_color="#0056b3", command=self._toggle_play_global)
        self.btn_play_mix.pack(side="left", padx=10, pady=10)

        btn_apply_times = ctk.CTkButton(bot_frame, text="Aplicar Tiempos", fg_color="#ffc107", text_color="black", hover_color="#d39e00", command=self._apply_timing_changes)
        btn_apply_times.pack(side="left", padx=5)

        btn_reload_studio = ctk.CTkButton(bot_frame, text="🔄 Recargar Mezcla", width=120, command=self._refresh_tab3)
        btn_reload_studio.pack(side="left", padx=5)

        # Exportar
        self.btn_export_video = ctk.CTkButton(bot_frame, text="🎬 Exportar Video Doblado", fg_color="#6f42c1", hover_color="#59359a", command=self._export_video)
        self.btn_export_video.pack(side="right", padx=(5, 10), pady=10)

        self.btn_export_audio = ctk.CTkButton(bot_frame, text="💾 Exportar Audio Doblado", font=("Arial", 13, "bold"), fg_color="#28a745", hover_color="#218838", command=self._export_audio)
        self.btn_export_audio.pack(side="right", padx=5, pady=10)

    def _refresh_tab3(self):
        for w in self.mid_scroll.winfo_children():
            w.destroy()
        self.segment_rows.clear()
        self._update_delete_button_state()

        if not self.processor or not self.processor.original_audio:
            return

        # Procesar todos los segmentos y crear filas
        for seg in self.processor.metadata:
            try:
                _, ratio = self.processor.process_segment(seg)
                self._add_segment_row(seg, ratio)
            except Exception as e:
                print(f"[WARN] Error procesando segmento {seg.get('filename')}: {e}")

        self._update_waveforms()

        # Activar/desactivar botón de exportar video
        has_video = bool(self.project_paths.get("video_file") and os.path.exists(self.project_paths["video_file"]))
        self.btn_export_video.configure(state="normal" if has_video else "disabled")

    def _add_segment_row(self, segment, ratio):
        is_selected = (self.selected_segment_id == segment.get("id"))
        row = ctk.CTkFrame(
            self.mid_scroll,
            border_width=2 if is_selected else 0,
            border_color="#ffe600" if is_selected else "#3d3d3d"
        )
        row.pack(fill="x", pady=3, padx=5)
        row.grid_columnconfigure(2, weight=1)

        btn_play = ctk.CTkButton(row, text="▶", width=30)
        btn_play.configure(command=lambda s=segment, b=btn_play: self._toggle_play_segment_slice(s, b))
        btn_play.grid(row=0, column=0, padx=5, pady=4)

        lbl_file = ctk.CTkLabel(row, text=segment.get("filename", ""), width=95, anchor="w", cursor="hand2")
        lbl_file.grid(row=0, column=1, padx=4, pady=4)
        lbl_file.bind("<Button-1>", lambda e, s=segment: self._select_segment_from_ui(s))

        lbl_text = ctk.CTkLabel(row, text=segment.get("translated", ""), wraplength=400, justify="left", anchor="w", cursor="hand2")
        lbl_text.grid(row=0, column=2, padx=8, pady=4, sticky="ew")
        lbl_text.bind("<Button-1>", lambda e, s=segment: self._select_segment_from_ui(s))

        ctrls = ctk.CTkFrame(row, fg_color="transparent")
        ctrls.grid(row=0, column=3, padx=5, pady=4, sticky="e")

        ctk.CTkLabel(ctrls, text="Inicio:").pack(side="left", padx=2)
        ent_start = ctk.CTkEntry(ctrls, width=70)
        ent_start.insert(0, str(segment.get("start_ms", 0)))
        ent_start.pack(side="left", padx=2)

        ctk.CTkLabel(ctrls, text=f"Fin: {segment.get('end_ms', 0)}ms", text_color="#aaaaaa").pack(side="left", padx=6)

        ctk.CTkLabel(ctrls, text="Ratio:").pack(side="left", padx=2)
        ent_ratio = ctk.CTkEntry(ctrls, width=55)
        ent_ratio.insert(0, f"{ratio:.2f}")
        ent_ratio.pack(side="left", padx=2)

        btn_gen = ctk.CTkButton(ctrls, text="Ajustar", width=70, command=lambda s=segment, e=ent_ratio: self._regenerate_segment(s, e))
        btn_gen.pack(side="left", padx=4)

        self.segment_rows[segment["id"]] = {
            "entry_start": ent_start,
            "entry_ratio": ent_ratio,
            "btn_play": btn_play
        }

    def _regenerate_segment(self, segment, entry_widget):
        try:
            r = float(entry_widget.get().strip())
            self.processor.process_segment(segment, manual_ratio=r)
            self._update_waveforms()
            messagebox.showinfo("Éxito", f"Segmento {segment.get('filename')} recalculado con ratio {r:.2f}.")
        except Exception as e:
            messagebox.showerror("Error", f"Ratio inválido o error al procesar: {e}")

    def _apply_timing_changes(self):
        if not self.processor:
            return
        try:
            for seg in self.processor.metadata:
                sid = seg.get("id")
                if sid in self.segment_rows:
                    val = int(self.segment_rows[sid]["entry_start"].get().strip())
                    seg["start_ms"] = max(0, val)

            self.processor.recalculate_end_times()
            self.pm.save_project_metadata(self.current_project, self.processor.metadata)
            self._refresh_tab3()
            messagebox.showinfo("Éxito", "Tiempos actualizados y proyecto recalculado.")
        except ValueError:
            messagebox.showerror("Error", "Los tiempos de inicio deben ser números enteros válidos.")

    def _reset_dubbed_positions(self):
        """Restaura todos los segmentos doblados a sus marcas y duraciones originales en español."""
        if not self.processor or not self.processor.metadata:
            return

        if not messagebox.askyesno("Confirmar Reseteo", "¿Deseas restaurar todos los segmentos a sus posiciones originales en español?"):
            return

        for seg in self.processor.metadata:
            orig_s = seg.get("orig_start_ms", seg.get("start_ms", 0))
            orig_e = seg.get("orig_end_ms", seg.get("end_ms", 0))
            seg["start_ms"] = orig_s
            seg["end_ms"] = orig_e

            # Obtener duración pura del archivo y calcular ratio original
            fname = seg.get("filename", "")
            fpath = os.path.join(self.project_paths["audios_dir"], fname)
            raw_dur = 0
            if os.path.exists(fpath):
                try:
                    raw_dur = len(AudioSegment.from_file(fpath))
                except Exception:
                    pass

            target_dur = max(300, orig_e - orig_s)
            orig_ratio = raw_dur / target_dur if (raw_dur > 0 and target_dur > 0) else 1.0
            orig_ratio = max(0.5, min(orig_ratio, 5.0))

            try:
                self.processor.process_segment(seg, manual_ratio=orig_ratio)
            except Exception as e:
                print(f"[WARN] Error procesando reseteo para {fname}: {e}")

        self.selected_segment_id = None
        self._update_delete_button_state()
        self.processor.recalculate_end_times()
        self.pm.save_project_metadata(self.current_project, self.processor.metadata)
        self._refresh_tab3()
        messagebox.showinfo("Reseteado", "Todos los segmentos han sido restaurados a sus posiciones originales.")

    # ----------------------------------------------------------
    # HERRAMIENTAS DE EDICIÓN: CUCHILLA (RAZOR) Y SUPRESIÓN
    # ----------------------------------------------------------
    def _set_tool_mode(self, mode):
        """Alterna entre el modo Puntero/Selección ('SELECT') y el modo Cuchilla ('RAZOR')."""
        self.active_tool = mode
        if mode == "SELECT":
            if self.btn_tool_select:
                self.btn_tool_select.configure(fg_color="#1f6aa5")
            if self.btn_tool_razor:
                self.btn_tool_razor.configure(fg_color="#333333")
            if self.dub_canvas:
                self.dub_canvas.get_tk_widget().configure(cursor="")
            if self.razor_guide_line:
                try:
                    self.razor_guide_line.remove()
                except Exception:
                    pass
                self.razor_guide_line = None
                if self.dub_canvas:
                    self.dub_canvas.draw_idle()
            if hasattr(self, 'lbl_dub_hover'):
                self.lbl_dub_hover.configure(text="")
        elif mode == "RAZOR":
            if self.btn_tool_select:
                self.btn_tool_select.configure(fg_color="#333333")
            if self.btn_tool_razor:
                self.btn_tool_razor.configure(fg_color="#c62828")
            if self.dub_canvas:
                self.dub_canvas.get_tk_widget().configure(cursor="crosshair")
            if hasattr(self, 'lbl_dub_hover'):
                self.lbl_dub_hover.configure(text="✂️ Modo Cuchilla activo: Haz clic sobre la onda doblada para dividir el audio")

    def _find_segment_at_ms(self, ms):
        """Busca y retorna el segmento que abarca el instante de tiempo en ms."""
        if not self.processor or not self.processor.metadata:
            return None
        for seg in self.processor.metadata:
            s = seg.get("start_ms", 0)
            e = seg.get("end_ms", 0)
            if s <= ms <= e:
                return seg
        return None

    def _split_segment(self, segment, cut_ms):
        """Divide el archivo de audio del segmento en dos fragmentos y los añade al timeline."""
        if not self.processor or not self.project_paths or not segment:
            return

        start_ms = segment.get("start_ms", 0)
        offset_ms = int(cut_ms - start_ms)

        fname = segment.get("filename", "")
        fpath = os.path.join(self.project_paths["audios_dir"], fname)
        if not os.path.exists(fpath):
            messagebox.showwarning("Atención", f"No se encontró el archivo de audio: {fname}")
            return

        # Cargar audio en memoria o desde disco
        audio = self.processor.processed_segments.get(fname)
        if not audio:
            try:
                audio = AudioSegment.from_file(fpath)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar el audio para cortar: {e}")
                return

        audio_len = len(audio)
        if offset_ms < 60 or offset_ms > (audio_len - 60):
            if hasattr(self, 'lbl_dub_hover'):
                self.lbl_dub_hover.configure(text="⚠️ Corte demasiado cercano al extremo (mínimo 60 ms)")
            return

        part1_audio = audio[:offset_ms]
        part2_audio = audio[offset_ms:]

        # Generar nombres únicos de archivo
        base, ext = os.path.splitext(fname)
        idx = 1
        part1_name = f"{base}_a{ext}"
        part2_name = f"{base}_b{ext}"
        while os.path.exists(os.path.join(self.project_paths["audios_dir"], part2_name)):
            part1_name = f"{base}_p{idx}a{ext}"
            part2_name = f"{base}_p{idx}b{ext}"
            idx += 1

        part1_path = os.path.join(self.project_paths["audios_dir"], part1_name)
        part2_path = os.path.join(self.project_paths["audios_dir"], part2_name)

        try:
            part1_audio.export(part1_path, format="wav")
            part2_audio.export(part2_path, format="wav")
        except Exception as e:
            messagebox.showerror("Error al exportar", f"No se pudieron guardar las partes cortadas: {e}")
            return

        # Calcular proporción de las marcas de anclaje originales
        orig_s = segment.get("orig_start_ms", start_ms)
        orig_e = segment.get("orig_end_ms", segment.get("end_ms", start_ms + audio_len))
        orig_dur = max(0, orig_e - orig_s)
        orig_mid = int(orig_s + (orig_dur * (offset_ms / max(1, audio_len))))

        # Crear los dos nuevos segmentos
        seg_idx = self.processor.metadata.index(segment)

        seg_a = dict(segment)
        seg_a["id"] = f"{segment['id']}_a"
        seg_a["filename"] = part1_name
        seg_a["start_ms"] = start_ms
        seg_a["end_ms"] = start_ms + len(part1_audio)
        seg_a["orig_start_ms"] = orig_s
        seg_a["orig_end_ms"] = orig_mid

        seg_b = dict(segment)
        seg_b["id"] = f"{segment['id']}_b"
        seg_b["filename"] = part2_name
        seg_b["start_ms"] = start_ms + len(part1_audio)
        seg_b["end_ms"] = start_ms + len(part1_audio) + len(part2_audio)
        seg_b["orig_start_ms"] = orig_mid
        seg_b["orig_end_ms"] = orig_e

        # Reemplazar segmento original por ambas mitades
        self.processor.metadata[seg_idx:seg_idx + 1] = [seg_a, seg_b]
        self.processor.processed_segments[part1_name] = part1_audio
        self.processor.processed_segments[part2_name] = part2_audio

        # Seleccionar automáticamente la parte B
        self.selected_segment_id = seg_b["id"]

        self.processor.recalculate_end_times()
        self.pm.save_project_metadata(self.current_project, self.processor.metadata)
        self._refresh_tab3()
        self._refresh_tab2()
        self._update_delete_button_state()
        if hasattr(self, 'lbl_dub_hover'):
            self.lbl_dub_hover.configure(text=f"✂️ Segmento dividido en {cut_ms} ms: [{seg_a['id']}] y [{seg_b['id']}]")

    def _split_at_playhead(self):
        """Divide el segmento que se encuentra en la posición actual del cursor de reproducción."""
        if not self.processor or not self.processor.metadata:
            return
        cur_pos = int(self.seek_slider.get())
        seg = self._find_segment_at_ms(cur_pos)
        if not seg:
            messagebox.showinfo("Corte en Cabezal", f"No hay ningún segmento de audio bajo el cabezal ({cur_pos} ms).")
            return
        self._split_segment(seg, cur_pos)

    def _delete_selected_segment(self):
        """Elimina el segmento seleccionado del timeline liberando su espacio."""
        if not self.selected_segment_id or not self.processor:
            return

        target = None
        for s in self.processor.metadata:
            if s.get("id") == self.selected_segment_id:
                target = s
                break

        if not target:
            return

        # Remover de la lista de metadatos y de caché
        self.processor.metadata.remove(target)
        fname = target.get("filename")
        if fname in self.processor.processed_segments:
            del self.processor.processed_segments[fname]

        deleted_id = self.selected_segment_id
        self.selected_segment_id = None
        self._update_delete_button_state()

        self.processor.recalculate_end_times()
        self.pm.save_project_metadata(self.current_project, self.processor.metadata)
        self._refresh_tab3()
        self._refresh_tab2()

        if hasattr(self, 'lbl_dub_hover'):
            self.lbl_dub_hover.configure(text=f"🗑️ Fragmento [{deleted_id}] eliminado. Espacio liberado.")

    def _update_delete_button_state(self):
        """Habilita o deshabilita el botón de suprimir según haya un segmento seleccionado."""
        if not hasattr(self, 'btn_delete_seg') or self.btn_delete_seg is None:
            return
        if self.selected_segment_id:
            self.btn_delete_seg.configure(state="normal", fg_color="#c62828")
        else:
            self.btn_delete_seg.configure(state="disabled", fg_color="#2b2b2b")

    def _on_key_delete(self, event):
        """Manejador del atajo Delete/BackSpace para suprimir el segmento seleccionado."""
        widget = self.focus_get()
        if isinstance(widget, (tk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox)):
            return
        self._delete_selected_segment()

    def _on_key_shortcut(self, event):
        """Manejador de los atajos de teclado 'C' (cuchilla) y 'V' (selección)."""
        widget = self.focus_get()
        if isinstance(widget, (tk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox)):
            return
        char = event.char.lower() if hasattr(event, 'char') else ''
        if char == "c":
            self._set_tool_mode("RAZOR")
        elif char == "v":
            self._set_tool_mode("SELECT")

    def _select_segment_from_ui(self, segment):
        """Permite seleccionar un segmento al hacer clic en su fila en la lista inferior."""
        if not segment:
            return
        prev = self.selected_segment_id
        self.selected_segment_id = segment.get("id")
        self._update_delete_button_state()
        if prev != self.selected_segment_id:
            self._update_waveforms()

    def _update_waveforms(self):
        if not self.processor or not self.processor.original_audio:
            return

        # Duración total en ms
        mix = self.processor.mix_dubbed_audio()
        duration_ms = len(mix) if mix else len(self.processor.original_audio)
        self.total_duration_ms = max(1, duration_ms)
        self.seek_slider.configure(to=self.total_duration_ms)
        self._update_time_label()

        # 1. Marcas fijas del audio original en español (Ground Truth inmutable con texto original)
        orig_segs_info = []
        for s in self.processor.metadata:
            s_orig = s.get("orig_start_ms", s.get("start_ms", 0))
            e_orig = s.get("orig_end_ms", s.get("end_ms", 0))
            orig_segs_info.append((s_orig, e_orig, s.get("original", ""), s.get("id", "")))

        # 2. Marcas dinámicas del audio doblado (Editables con texto traducido e ID)
        dub_segs_info = []
        for s in self.processor.metadata:
            dub_segs_info.append((s.get("start_ms", 0), s.get("end_ms", 0), s.get("translated", ""), s.get("id", "")))

        # Forma de onda original (Celeste de alto contraste #38bdf8 con marcas fijas de corte en español - NUNCA SE MUEVEN)
        orig_data = self.processor.get_waveform_data(self.processor.original_audio)
        self._draw_waveform_canvas(self.orig_canvas_frame, orig_data, '#38bdf8', is_dubbed=False, segments=orig_segs_info, cut_color='#ff5252')

        # Forma de onda doblada (Naranja con marcas dinámicas de doblaje y resaltado de selección)
        mix_data = self.processor.get_waveform_data(mix)
        self._draw_waveform_canvas(self.dub_canvas_frame, mix_data, '#ff7f0e', is_dubbed=True, segments=dub_segs_info, cut_color='#ff5252')

    def _draw_waveform_canvas(self, frame, samples, color, is_dubbed=False, segments=None, cut_color='#ff5252'):
        import numpy as np
        for w in frame.winfo_children():
            w.destroy()

        fig, (ax_wave, ax_text) = plt.subplots(
            nrows=2, ncols=1,
            figsize=(4, 1.4),
            dpi=80,
            gridspec_kw={'height_ratios': [2.2, 1.0], 'hspace': 0.06},
            sharex=True
        )
        fig.patch.set_facecolor('#2b2b2b')
        ax_wave.set_facecolor('#2b2b2b')
        ax_text.set_facecolor('#222222')

        # Eje X en milisegundos reales (0 a total_duration_ms)
        n = len(samples)
        if n > 0:
            x_coords = np.linspace(0, self.total_duration_ms, n)
            ax_wave.plot(x_coords, samples, color=color, linewidth=0.6)
            max_val = max(abs(float(samples.max())), abs(float(samples.min()))) if n > 0 else 1.0
            if max_val > 0:
                ax_wave.set_ylim(-max_val * 1.15, max_val * 1.15)
        ax_wave.set_xlim(0, self.total_duration_ms)

        # Marcas de cortes de cada frase (líneas discontinuas y sombreado translúcido)
        if segments:
            for seg_item in segments:
                s_ms = seg_item[0]
                e_ms = seg_item[1]
                seg_id = seg_item[3] if len(seg_item) > 3 else ""
                is_selected = bool(is_dubbed and self.selected_segment_id and seg_id == self.selected_segment_id)

                if is_selected:
                    # Resaltado amarillo neón para clip seleccionado
                    ax_wave.axvspan(s_ms, e_ms, color='#ffe600', alpha=0.22, zorder=3)
                    ax_wave.axvline(x=s_ms, color='#ffe600', linestyle='-', linewidth=2.0, zorder=6)
                    ax_wave.axvline(x=e_ms, color='#ffe600', linestyle='-', linewidth=2.0, zorder=6)
                else:
                    ax_wave.axvspan(s_ms, e_ms, color='white', alpha=0.06)
                    ax_wave.axvline(x=s_ms, color=cut_color, linestyle='--', linewidth=0.85, alpha=0.85)
                    ax_wave.axvline(x=e_ms, color=cut_color, linestyle='--', linewidth=0.85, alpha=0.85)

        # Cajas de texto en la franja inferior (ax_text)
        ax_text.set_ylim(0, 1)
        ax_text.set_xlim(0, self.total_duration_ms)
        if segments:
            for seg_item in segments:
                s_ms = seg_item[0]
                e_ms = seg_item[1]
                text_content = seg_item[2] if len(seg_item) > 2 else ""
                seg_id = seg_item[3] if len(seg_item) > 3 else ""
                is_selected = bool(is_dubbed and self.selected_segment_id and seg_id == self.selected_segment_id)

                dur_ms = e_ms - s_ms
                if dur_ms <= 80:
                    continue

                pad = min(15.0, dur_ms * 0.04)
                rect_x = s_ms + pad
                rect_w = max(10.0, dur_ms - (pad * 2))

                box_bg = ('#5c3d00' if is_selected else '#4a2800') if is_dubbed else '#0c3559'
                box_border = '#ffe600' if is_selected else ('#f97316' if is_dubbed else '#38bdf8')
                border_w = 2.0 if is_selected else 0.9

                rect = patches.FancyBboxPatch(
                    (rect_x, 0.1), rect_w, 0.8,
                    boxstyle="round,pad=0.02,rounding_size=0.1",
                    facecolor=box_bg,
                    edgecolor=box_border,
                    linewidth=border_w,
                    alpha=0.95,
                    zorder=4 if is_selected else 2
                )
                ax_text.add_patch(rect)

                # Cálculo de truncamiento con elipsis según duración
                max_chars = max(4, int(dur_ms / 85))
                clean_text = text_content.strip()
                if len(clean_text) > max_chars:
                    display_text = clean_text[:max(1, max_chars - 2)] + "…"
                else:
                    display_text = clean_text

                mid_x = s_ms + (dur_ms / 2.0)
                ax_text.text(
                    mid_x, 0.5, display_text,
                    color='#ffe600' if is_selected else '#f1f5f9',
                    fontsize=7.5,
                    fontweight='bold' if is_selected else 'normal',
                    ha='center', va='center',
                    clip_on=True
                )

        # Cabezal de reproducción (Playhead) - línea vertical visible en amarillo neón (#ffe600)
        cur_pos = self.seek_slider.get()
        cursor_wave = ax_wave.axvline(x=cur_pos, color='#ffe600', linewidth=1.8, zorder=10)
        cursor_text = ax_text.axvline(x=cur_pos, color='#ffe600', linewidth=1.8, zorder=10)

        ax_wave.axis('off')
        ax_text.axis('off')
        plt.subplots_adjust(left=0.005, right=0.995, top=0.98, bottom=0.02)

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)

        # Guardar referencias y conectar eventos
        if is_dubbed:
            self.dub_ax = ax_wave
            self.dub_ax_text = ax_text
            self.dub_canvas = canvas
            self.dub_cursor = cursor_wave
            self.dub_cursor_text = cursor_text
            if self.active_tool == "RAZOR":
                canvas.get_tk_widget().configure(cursor="crosshair")
            # Conectar eventos de manipulación de segmentos (mover, estirar/comprimir)
            canvas.mpl_connect('button_press_event', self._on_timeline_press)
            canvas.mpl_connect('motion_notify_event', self._on_timeline_motion)
            canvas.mpl_connect('button_release_event', self._on_timeline_release)
            canvas.mpl_connect('figure_leave_event', self._on_timeline_leave)
        else:
            self.orig_ax = ax_wave
            self.orig_ax_text = ax_text
            self.orig_canvas = canvas
            self.orig_cursor = cursor_wave
            self.orig_cursor_text = cursor_text
            canvas.mpl_connect('button_press_event', self._on_waveform_click)
            canvas.mpl_connect('motion_notify_event', self._on_orig_motion)
            canvas.mpl_connect('figure_leave_event', self._on_orig_leave)

    def _on_timeline_motion(self, event):
        """Maneja el hover (cambio de cursor), el modo cuchilla y el arrastre activo (mover o estirar)."""
        if not self.processor or not self.processor.metadata or not self.dub_canvas:
            return

        canvas_widget = self.dub_canvas.get_tk_widget()

        # CASO 0: Modo Cuchilla (Razor Tool)
        if self.active_tool == "RAZOR":
            if event.xdata is None or (hasattr(self, 'dub_ax') and event.inaxes != self.dub_ax):
                if self.razor_guide_line:
                    try:
                        self.razor_guide_line.remove()
                    except Exception:
                        pass
                    self.razor_guide_line = None
                    self.dub_canvas.draw_idle()
                return

            cut_ms = int(event.xdata)
            if self.razor_guide_line is None:
                self.razor_guide_line = self.dub_ax.axvline(x=cut_ms, color='#ff1744', linestyle='--', linewidth=1.5, zorder=25)
            else:
                self.razor_guide_line.set_xdata([cut_ms, cut_ms])
            self.dub_canvas.draw_idle()

            target_seg = self._find_segment_at_ms(cut_ms)
            if target_seg:
                if hasattr(self, 'lbl_dub_hover'):
                    self.lbl_dub_hover.configure(
                        text=f"✂️ Cuchilla en {cut_ms} ms | Clic para dividir [{target_seg.get('id', '')}]"
                    )
            else:
                if hasattr(self, 'lbl_dub_hover'):
                    self.lbl_dub_hover.configure(text=f"✂️ Cuchilla en {cut_ms} ms (fuera de segmento)")
            return

        # Limpiar línea guía si no estamos en modo cuchilla
        if self.razor_guide_line:
            try:
                self.razor_guide_line.remove()
            except Exception:
                pass
            self.razor_guide_line = None
            self.dub_canvas.draw_idle()

        # CASO 1: Arrastre Activo (El usuario tiene el botón presionado y mueve el mouse)
        if self.drag_mode is not None:
            if event.xdata is None:
                return

            self.drag_has_moved = True
            delta_x = event.xdata - self.drag_start_x

            if self.drag_mode == "MOVE":
                dur = self.orig_seg_end - self.orig_seg_start
                new_start = max(0, self.orig_seg_start + delta_x)
                new_end = new_start + dur
                if new_end > self.total_duration_ms:
                    new_end = self.total_duration_ms
                    new_start = max(0, new_end - dur)

                # Actualizar el rectángulo fantasma
                if self.ghost_patch:
                    self.ghost_patch.remove()
                self.ghost_patch = self.dub_ax.axvspan(new_start, new_end, color='#00e5ff', alpha=0.35, zorder=5)
                self.dub_canvas.draw_idle()
                self.lbl_time.configure(text=f"Mover: {int(new_start)}ms → {int(new_end)}ms")

            elif self.drag_mode == "RESIZE":
                new_end = max(self.orig_seg_start + 300, self.orig_seg_end + delta_x)
                if new_end > self.total_duration_ms:
                    new_end = self.total_duration_ms

                target_dur = max(300, new_end - self.orig_seg_start)
                ratio = self.orig_clip_raw_duration / target_dur if self.orig_clip_raw_duration > 0 else 1.0
                ratio = max(0.5, min(ratio, 5.0))

                # Actualizar el rectángulo fantasma
                if self.ghost_patch:
                    self.ghost_patch.remove()
                self.ghost_patch = self.dub_ax.axvspan(self.orig_seg_start, new_end, color='#ffc107', alpha=0.35, zorder=5)
                self.dub_canvas.draw_idle()
                self.lbl_time.configure(text=f"Fin: {int(new_end)}ms | Ratio: {ratio:.2f}x")

            return

        # CASO 2: Hover (Detección para cambiar cursor a ↔ o ✋ y mostrar texto completo en cabecera)
        if event.xdata is None:
            canvas_widget.configure(cursor="")
            if hasattr(self, 'lbl_dub_hover'):
                self.lbl_dub_hover.configure(text="")
            return

        hovered_text = ""
        tol = max(200.0, self.total_duration_ms * 0.015)
        cursor_type = ""

        for seg in self.processor.metadata:
            s_ms = seg.get("start_ms", 0)
            e_ms = seg.get("end_ms", 0)

            if s_ms <= event.xdata <= e_ms:
                hovered_text = f"[{seg.get('id', '')}] {seg.get('translated', '')}"

            if hasattr(self, 'dub_ax') and event.inaxes == self.dub_ax:
                # Borde derecho: Estirar/Comprimir (↔)
                if abs(event.xdata - e_ms) <= tol:
                    cursor_type = "sb_h_double_arrow"
                # Cuerpo del segmento: Desplazar (✋)
                elif (s_ms + tol) < event.xdata < (e_ms - tol):
                    cursor_type = "fleur"

        canvas_widget.configure(cursor=cursor_type)
        if hasattr(self, 'lbl_dub_hover'):
            self.lbl_dub_hover.configure(text=hovered_text)

    def _on_timeline_press(self, event):
        """Detecta si el clic es para dividir (cuchilla), seleccionar, mover, estirar o hacer seek."""
        if event.button != 1 or event.xdata is None or not self.processor:
            return

        click_x = event.xdata
        click_ms = int(click_x)

        # 1. MODO CUCHILLA: Dividir el segmento cliqueado inmediatamente
        if self.active_tool == "RAZOR":
            target_seg = self._find_segment_at_ms(click_ms)
            if target_seg:
                self._split_segment(target_seg, click_ms)
            return

        # 2. MODO SELECCIÓN: Identificar si se seleccionó un segmento
        target_seg = self._find_segment_at_ms(click_ms)
        prev_selected = self.selected_segment_id
        if target_seg:
            self.selected_segment_id = target_seg.get("id")
        else:
            self.selected_segment_id = None
        self._update_delete_button_state()
        if prev_selected != self.selected_segment_id:
            self._update_waveforms()

        # Si el clic no fue en el eje de la onda de audio (ax_wave), hacer seek directamente
        if hasattr(self, 'dub_ax') and event.inaxes != self.dub_ax:
            self.drag_mode = "SEEK"
            self._on_waveform_click(event)
            return

        tol = max(200.0, self.total_duration_ms * 0.015)

        for seg in self.processor.metadata:
            s_ms = seg.get("start_ms", 0)
            e_ms = seg.get("end_ms", 0)

            # 1. Clic en el borde derecho -> RESIZE
            if abs(click_x - e_ms) <= tol:
                self.drag_mode = "RESIZE"
                self.drag_segment = seg
                self.drag_start_x = click_x
                self.orig_seg_start = s_ms
                self.orig_seg_end = e_ms
                self.drag_has_moved = False

                fname = seg.get("filename", "")
                fpath = os.path.join(self.project_paths["audios_dir"], fname)
                if os.path.exists(fpath):
                    try:
                        self.orig_clip_raw_duration = len(AudioSegment.from_file(fpath))
                    except Exception:
                        self.orig_clip_raw_duration = max(300, e_ms - s_ms)
                else:
                    self.orig_clip_raw_duration = max(300, e_ms - s_ms)

                self.ghost_patch = self.dub_ax.axvspan(s_ms, e_ms, color='#ffc107', alpha=0.35, zorder=5)
                self.dub_canvas.draw_idle()
                return

            # 2. Clic en el cuerpo -> MOVE
            if (s_ms + tol) < click_x < (e_ms - tol):
                self.drag_mode = "MOVE"
                self.drag_segment = seg
                self.drag_start_x = click_x
                self.orig_seg_start = s_ms
                self.orig_seg_end = e_ms
                self.drag_has_moved = False

                self.ghost_patch = self.dub_ax.axvspan(s_ms, e_ms, color='#00e5ff', alpha=0.35, zorder=5)
                self.dub_canvas.draw_idle()
                return

        # 3. Clic fuera de cualquier segmento -> SEEK normal
        self.drag_mode = "SEEK"
        self._on_waveform_click(event)

    def _on_timeline_release(self, event):
        """Aplica los cambios al soltar el mouse tras mover o estirar."""
        if self.ghost_patch:
            try:
                self.ghost_patch.remove()
            except Exception:
                pass
            self.ghost_patch = None
            if self.dub_canvas:
                self.dub_canvas.draw_idle()

        if self.dub_canvas:
            if self.active_tool == "RAZOR":
                self.dub_canvas.get_tk_widget().configure(cursor="crosshair")
            else:
                self.dub_canvas.get_tk_widget().configure(cursor="")

        mode = self.drag_mode
        seg = self.drag_segment
        has_moved = self.drag_has_moved

        self.drag_mode = None
        self.drag_segment = None
        self.drag_has_moved = False

        if not has_moved or event.xdata is None or not seg:
            if mode in ("MOVE", "RESIZE") and event.xdata is not None:
                self._on_waveform_click(event)
            return

        delta_x = event.xdata - self.drag_start_x

        if mode == "MOVE":
            dur = self.orig_seg_end - self.orig_seg_start
            new_start = int(max(0, self.orig_seg_start + delta_x))
            new_end = int(new_start + dur)
            if new_end > self.total_duration_ms:
                new_end = int(self.total_duration_ms)
                new_start = int(max(0, new_end - dur))

            seg["start_ms"] = new_start
            seg["end_ms"] = new_end
            self.processor.recalculate_end_times()
            self.pm.save_project_metadata(self.current_project, self.processor.metadata)
            self._refresh_tab3()

        elif mode == "RESIZE":
            new_end = int(max(self.orig_seg_start + 300, self.orig_seg_end + delta_x))
            if new_end > self.total_duration_ms:
                new_end = int(self.total_duration_ms)

            seg["end_ms"] = new_end
            target_dur = max(300, new_end - self.orig_seg_start)
            ratio = self.orig_clip_raw_duration / target_dur if self.orig_clip_raw_duration > 0 else 1.0
            ratio = max(0.5, min(ratio, 5.0))

            # Aplicar atempo con ffmpeg para actualizar el audio estirado/comprimido
            try:
                self.processor.process_segment(seg, manual_ratio=ratio)
            except Exception as e:
                print(f"[WARN] Error aplicando atempo tras resize: {e}")

            self.processor.recalculate_end_times()
            self.pm.save_project_metadata(self.current_project, self.processor.metadata)
            self._refresh_tab3()

    def _on_timeline_leave(self, event):
        """Restaura el cursor si el mouse sale del canvas y limpia el preview."""
        if self.drag_mode is None and self.dub_canvas:
            if self.active_tool == "RAZOR":
                self.dub_canvas.get_tk_widget().configure(cursor="crosshair")
            else:
                self.dub_canvas.get_tk_widget().configure(cursor="")
        if self.razor_guide_line:
            try:
                self.razor_guide_line.remove()
            except Exception:
                pass
            self.razor_guide_line = None
            if self.dub_canvas:
                self.dub_canvas.draw_idle()
        if hasattr(self, 'lbl_dub_hover'):
            self.lbl_dub_hover.configure(text="")

    def _on_orig_motion(self, event):
        """Muestra el texto completo en español al pasar el mouse sobre la pista original."""
        if not self.processor or not self.processor.metadata:
            return
        if event.xdata is None:
            if hasattr(self, 'lbl_orig_hover'):
                self.lbl_orig_hover.configure(text="")
            return

        x = event.xdata
        hovered_text = ""
        for seg in self.processor.metadata:
            s_orig = seg.get("orig_start_ms", seg.get("start_ms", 0))
            e_orig = seg.get("orig_end_ms", seg.get("end_ms", 0))
            if s_orig <= x <= e_orig:
                hovered_text = f"[{seg.get('id', '')}] {seg.get('original', '')}"
                break

        if hasattr(self, 'lbl_orig_hover'):
            self.lbl_orig_hover.configure(text=hovered_text)

    def _on_orig_leave(self, event):
        """Limpia el texto de preview al salir del canvas original."""
        if hasattr(self, 'lbl_orig_hover'):
            self.lbl_orig_hover.configure(text="")

    def _update_playhead(self, current_ms):
        """Mueve la línea vertical sobre ambas ondas y cajas de texto en tiempo real de forma ultra ligera."""
        try:
            if self.orig_canvas:
                if self.orig_cursor:
                    self.orig_cursor.set_xdata([current_ms, current_ms])
                if self.orig_cursor_text:
                    self.orig_cursor_text.set_xdata([current_ms, current_ms])
                self.orig_canvas.draw_idle()
            if self.dub_canvas:
                if self.dub_cursor:
                    self.dub_cursor.set_xdata([current_ms, current_ms])
                if self.dub_cursor_text:
                    self.dub_cursor_text.set_xdata([current_ms, current_ms])
                self.dub_canvas.draw_idle()
        except Exception:
            pass

    def _on_waveform_click(self, event):
        """Salta la reproducción directamente al punto de la onda donde se hizo clic."""
        if event.xdata is not None and 0 <= event.xdata <= self.total_duration_ms:
            target_ms = int(event.xdata)
            self.seek_slider.set(target_ms)
            self._update_time_label()
            self._update_playhead(target_ms)
            if self.playing_id == "global":
                self._restart_global_playback()

    def _toggle_mute_orig(self):
        self.mute_original = not self.mute_original
        self.btn_mute_orig.configure(fg_color="#dc3545" if self.mute_original else ["#3B8ED0", "#1F6AA5"])

    def _toggle_mute_dub(self):
        self.mute_dubbed = not self.mute_dubbed
        self.btn_mute_dub.configure(fg_color="#dc3545" if self.mute_dubbed else ["#3B8ED0", "#1F6AA5"])

    def _on_seek_change(self, val):
        self._update_time_label()
        self._update_playhead(float(val))


    def _on_seek_release(self, event):
        self.is_dragging = False
        if self.playing_id == "global":
            self._restart_global_playback()

    def _update_time_label(self):
        cur = int(self.seek_slider.get() / 1000)
        tot = int(self.total_duration_ms / 1000)
        self.lbl_time.configure(text=f"{cur//60:02d}:{cur%60:02d} / {tot//60:02d}:{tot%60:02d}")

    def _toggle_play_global(self):
        if not self.processor:
            return

        if self.playing_id == "global":
            self._stop_playback()
            self.btn_play_mix.configure(text="▶ Reproducir Mezcla")
            return

        mix = self.processor.get_current_mix(
            vol_orig=self.slider_vol_orig.get(),
            mute_orig=self.mute_original,
            vol_dub=self.slider_vol_dub.get(),
            mute_dub=self.mute_dubbed
        )
        if not mix:
            return

        start_ms = int(self.seek_slider.get())
        if start_ms >= len(mix):
            start_ms = 0
            self.seek_slider.set(0)

        audio_slice = mix[start_ms:]
        self.btn_play_mix.configure(text="⏹ Detener")
        self._play_audio_ffplay(audio_slice, self.btn_play_mix, "▶ Reproducir Mezcla", "global", start_offset=start_ms)

    def _restart_global_playback(self):
        self._stop_playback()
        self._toggle_play_global()

    def _toggle_play_segment_slice(self, segment, btn):
        seg_id = segment.get("id")
        if self.playing_id == seg_id:
            self._stop_playback()
            btn.configure(text="▶")
            return

        if not self.processor or not self.processor.original_audio:
            return

        start = segment.get("start_ms", 0)
        end = segment.get("end_ms", 0)
        orig_slice = self.processor.original_audio[start:end]

        fname = segment.get("filename")
        if fname in self.processor.processed_segments:
            dub_seg = self.processor.processed_segments[fname]
        else:
            dub_seg = AudioSegment.silent(duration=len(orig_slice))

        # Aplicar volúmenes
        vol_o = self.slider_vol_orig.get()
        vol_d = self.slider_vol_dub.get()
        db_o = -100 if self.mute_original or vol_o == 0 else 20 * math.log10(vol_o)
        db_d = -100 if self.mute_dubbed or vol_d == 0 else 20 * math.log10(vol_d)

        mixed = (orig_slice + db_o).overlay(dub_seg + db_d)
        btn.configure(text="⏹")
        self._play_audio_ffplay(mixed, btn, "▶", seg_id)

    def _play_audio_ffplay(self, audio_segment, btn_widget, reset_text, play_id, start_offset=0):
        self._stop_playback()
        self.playing_id = play_id
        self.play_start_offset = start_offset
        self.play_start_sys_time = time.time()

        temp_wav = os.path.join(self.processor.temp_dir, "play_temp.wav")
        audio_segment.export(temp_wav, format="wav")

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            self.playing_process = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", temp_wav],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=startupinfo
            )

            def _poll():
                if self.playing_id == play_id:
                    if play_id == "global" and not self.is_dragging:
                        elapsed = self.play_start_offset + (time.time() - self.play_start_sys_time) * 1000
                        if elapsed <= self.total_duration_ms:
                            self.seek_slider.set(elapsed)
                            self._update_time_label()
                            self._update_playhead(elapsed)

                    if self.playing_process and self.playing_process.poll() is None:
                        self.after(40, _poll)
                    else:
                        try:
                            btn_widget.configure(text=reset_text)
                        except Exception:
                            pass
                        self.playing_id = None
                        if play_id == "global" and not self.is_dragging:
                            self.seek_slider.set(0)
                            self._update_time_label()
                            self._update_playhead(0)

            self.after(40, _poll)

        except Exception:
            # Fallback
            from pydub.playback import play
            threading.Thread(target=play, args=(audio_segment,), daemon=True).start()
            self.playing_id = None

    def _stop_playback(self):
        if self.playing_process and self.playing_process.poll() is None:
            self.playing_process.terminate()
            self.playing_process.wait()
        self.playing_id = None

    def _export_audio(self):
        if not self.processor:
            return

        default_name = f"{self.current_project}_doblado.wav"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            initialfile=default_name,
            filetypes=[("WAV Audio", "*.wav"), ("MP3 Audio", "*.mp3")],
            title="Guardar Audio Doblado"
        )
        if not save_path:
            return

        try:
            self.processor.export_mix_audio(
                save_path,
                vol_orig=self.slider_vol_orig.get(),
                mute_orig=self.mute_original,
                vol_dub=self.slider_vol_dub.get(),
                mute_dub=self.mute_dubbed
            )
            messagebox.showinfo("Exportado", f"Audio guardado exitosamente en:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error al Exportar", str(e))

    def _export_video(self):
        video_file = self.project_paths.get("video_file")
        if not video_file or not os.path.exists(video_file):
            messagebox.showwarning("Atención", "El proyecto actual no tiene un video de origen (.mp4).")
            return

        default_name = f"{self.current_project}_video_doblado.mp4"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            initialfile=default_name,
            filetypes=[("Video MP4", "*.mp4")],
            title="Guardar Video Doblado"
        )
        if not save_path:
            return

        temp_audio = os.path.join(self.processor.temp_dir, "export_temp.wav")
        try:
            self.processor.export_mix_audio(
                temp_audio,
                vol_orig=self.slider_vol_orig.get(),
                mute_orig=self.mute_original,
                vol_dub=self.slider_vol_dub.get(),
                mute_dub=self.mute_dubbed
            )
            self.processor.export_video_with_audio(video_file, temp_audio, save_path)
            messagebox.showinfo("Exportado", f"Video con audio doblado generado exitosamente en:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error al Exportar Video", str(e))

    def on_closing(self):
        self._stop_playback()
        if self.processor:
            self.processor.cleanup()
        try:
            self.quit()
            self.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    app = AudioDubbingStudio()
    app.mainloop()
