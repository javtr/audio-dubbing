import os
import copy
import queue
import threading
import gc
import tkinter as tk
from tkinter import messagebox
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

try:
    import pygame
    pygame.mixer.init()
except Exception as e:
    print(f"[Warning] Pygame mixer init: {e}")

from core import (
    ProjectManager,
    WhisperAligner,
    PinokioClient,
    AudioProcessor,
    PlaybackEngine,
    ExportService
)
from ui.dialogs import NewProjectDialog
from ui.widgets import TopBar
from views import TabScriptView, TabDubbingView, TabStudioView


class AudioDubbingStudio(ctk.CTk):
    """Aplicación principal y orquestador central de Audio Dubbing Studio."""

    def __init__(self):
        super().__init__()
        self.title("Logic Imprint - Audio Dubbing Studio")
        self.geometry("1100x820")
        self.minsize(950, 700)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Servicios Core
        self.pm = ProjectManager()
        self.aligner = WhisperAligner()
        self.pinokio = PinokioClient()
        self.playback = PlaybackEngine()
        self.exporter = ExportService()
        self.processor = None

        # Estado del proyecto
        self.current_project = None
        self.project_paths = {}
        self.segments_data = []
        self.master_segments = []
        self.pinokio_connected = False

        # Cola thread-safe para actualizar la interfaz gráfica desde hilos secundarios
        self._gui_queue = queue.Queue()
        self._poll_gui_queue()

        # Construcción de la interfaz
        self._build_ui()
        self._check_pinokio_status_async()
        self._load_initial_project()

    def run_on_ui_thread(self, callback):
        """Encola una función para ejecutarse de forma segura en el hilo principal de Tkinter."""
        self._gui_queue.put(callback)

    def _poll_gui_queue(self):
        """Revisa periódicamente la cola y ejecuta tareas pendientes en el hilo principal."""
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

    def _build_ui(self):
        # 1. Barra superior
        self.top_bar = TopBar(
            self,
            on_project_changed=self._on_project_changed,
            on_new_project=self._show_new_project_dialog,
            on_check_pinokio=self._check_pinokio_status_async,
            on_free_vram=self._free_vram_action
        )
        self.top_bar.pack(fill="x", side="top")

        # 2. Pestañas de trabajo
        self.tabview = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        tab1 = self.tabview.add("1. Guion y Tiempos")
        tab2 = self.tabview.add("2. Doblaje (Pinokio)")
        tab3 = self.tabview.add("3. Estudio y Mezcla")

        self.view_script = TabScriptView(tab1, self)
        self.view_script.pack(fill="both", expand=True)

        self.view_dubbing = TabDubbingView(tab2, self)
        self.view_dubbing.pack(fill="both", expand=True)

        self.view_studio = TabStudioView(tab3, self)
        self.view_studio.pack(fill="both", expand=True)

    def _on_tab_changed(self):
        """Libera automáticamente VRAM de Whisper al cambiar a pestañas que usan Pinokio o Mezcla."""
        current_tab = self.tabview.get()
        if current_tab in ["2. Doblaje (Pinokio)", "3. Estudio y Mezcla"]:
            self.aligner.unload_model()

    def _show_new_project_dialog(self):
        NewProjectDialog(self, self._create_new_project)

    def _create_new_project(self, name, source_file, target_language="en"):
        try:
            safe_name, paths = self.pm.create_project(name, source_file, target_language)
            self._refresh_project_list(select_project=safe_name)
            lang_label = "Portugués (pt)" if target_language == "pt" else "Inglés (en)"
            messagebox.showinfo("Éxito", f"Proyecto '{safe_name}' [{lang_label}] creado correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear el proyecto: {e}")

    def _refresh_project_list(self, select_project=None):
        projects = self.pm.list_projects()
        self.top_bar.update_project_list(projects, select_project)
        if projects:
            target = select_project if select_project in projects else projects[0]
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

        # Actualizar indicador de idioma en la barra superior y título
        lang = self.pm.get_project_language(project_name)
        self.top_bar.set_project_language(lang)
        lang_tag = "Portugués (PT)" if lang == "pt" else "Inglés (EN)"
        self.title(f"Logic Imprint - Audio Dubbing Studio | {project_name} [{lang_tag}]")

        # Asegurar anclas fijas originales inmutables
        for seg in self.segments_data:
            if "orig_start_ms" not in seg:
                seg["orig_start_ms"] = seg.get("start_ms", 0)
            if "orig_end_ms" not in seg:
                seg["orig_end_ms"] = seg.get("end_ms", 0)

        # Cargar o inicializar master_segments (Ground Truth original)
        master = self.pm.load_master_metadata(project_name)
        if master:
            self.master_segments = master
        else:
            self.master_segments = copy.deepcopy(self.segments_data)
            self.pm.save_master_metadata(project_name, self.master_segments)

        # Inicializar AudioProcessor
        if self.project_paths.get("audio_file"):
            self.processor = AudioProcessor(
                self.project_paths["audio_file"],
                self.project_paths["audios_dir"],
                self.segments_data
            )
        else:
            self.processor = None

        self.notify_metadata_updated()

    def notify_metadata_updated(self):
        """Notifica a todas las vistas que los segmentos o tiempos del proyecto cambiaron."""
        self.view_script.refresh()
        self.view_dubbing.refresh()
        self.view_studio.refresh()

    def notify_audio_updated(self):
        """Notifica al estudio que hay nuevos audios sintetizados por Pinokio."""
        if self.processor and self.project_paths and "audios_dir" in self.project_paths:
            self.processor.preload_segments(self.project_paths["audios_dir"])
        self.view_studio.refresh()

    def _check_pinokio_status_async(self):
        def _check():
            online = self.pinokio.check_connection()
            self.pinokio_connected = online
            self.run_on_ui_thread(lambda: self.top_bar.set_pinokio_status(online))
        threading.Thread(target=_check, daemon=True).start()

    def _free_vram_action(self):
        try:
            self.aligner.unload_model()
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
            except Exception:
                pass
            messagebox.showinfo(
                "VRAM Liberada",
                "El modelo de Whisper ha sido descargado y la VRAM de la GPU ha sido liberada para Pinokio."
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo liberar la memoria: {e}")

    def on_closing(self):
        self.playback.stop()
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
