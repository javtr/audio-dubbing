import os
import json
import gc
import copy
import threading
from tkinter import messagebox
import customtkinter as ctk

class TabScriptView(ctk.CTkFrame):
    """Pestaña 1: Transcripción del audio original, generación de prompt para Gemini y sincronización con Whisper."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Panel Izquierdo: Transcripción y Asistente Gemini
        left_frame = ctk.CTkFrame(self)
        left_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")
        left_frame.grid_rowconfigure(2, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left_frame,
            text="Paso 1A: Transcripción y Prompt para Gemini",
            font=("Arial", 15, "bold")
        ).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        btn_bar = ctk.CTkFrame(left_frame, fg_color="transparent")
        btn_bar.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        self.btn_transcribe = ctk.CTkButton(btn_bar, text="🎙️ Transcribir Audio", command=self._start_transcribe_thread)
        self.btn_transcribe.pack(side="left", padx=(0, 5))

        self.btn_copy_prompt = ctk.CTkButton(
            btn_bar,
            text="📋 Copiar Prompt para Gemini",
            fg_color="#7b1fa2",
            hover_color="#4a148c",
            command=self._copy_gemini_prompt
        )
        self.btn_copy_prompt.pack(side="left", padx=5)

        self.txt_transcript = ctk.CTkTextbox(left_frame, font=("Arial", 12))
        self.txt_transcript.grid(row=2, column=0, padx=15, pady=10, sticky="nsew")

        self.lbl_t1_status = ctk.CTkLabel(left_frame, text="Listo.", text_color="#aaaaaa", font=("Arial", 11))
        self.lbl_t1_status.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="w")

        # Panel Derecho: Pegar JSON y Sincronización Whisper
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right_frame,
            text="Paso 1B: JSON de Gemini y Tiempos",
            font=("Arial", 15, "bold")
        ).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        json_btn_bar = ctk.CTkFrame(right_frame, fg_color="transparent")
        json_btn_bar.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        btn_save_json = ctk.CTkButton(json_btn_bar, text="💾 Guardar JSON", width=120, command=self._save_raw_json)
        btn_save_json.pack(side="left", padx=(0, 5))

        self.btn_align = ctk.CTkButton(
            json_btn_bar,
            text="⏱️ Sincronizar Tiempos (Whisper)",
            fg_color="#28a745",
            hover_color="#218838",
            command=self._start_align_thread
        )
        self.btn_align.pack(side="left", padx=5)

        self.txt_json = ctk.CTkTextbox(right_frame, font=("Consolas", 12))
        self.txt_json.grid(row=2, column=0, padx=15, pady=10, sticky="nsew")

        self.lbl_t1_align_status = ctk.CTkLabel(
            right_frame,
            text="Pega aquí el JSON devuelto por Gemini.",
            text_color="#aaaaaa",
            font=("Arial", 11)
        )
        self.lbl_t1_align_status.grid(row=3, column=0, padx=15, pady=(0, 10), sticky="w")

    def refresh(self):
        """Carga el JSON del proyecto actual en la caja de texto."""
        segments = self.app.segments_data
        if segments:
            formatted = json.dumps(segments, indent=2, ensure_ascii=False)
            self.txt_json.delete("1.0", "end")
            self.txt_json.insert("1.0", formatted)
            self.lbl_t1_align_status.configure(
                text=f"{len(segments)} segmentos cargados en secciones.json",
                text_color="#28a745"
            )
        else:
            self.txt_json.delete("1.0", "end")
            self.lbl_t1_align_status.configure(
                text="Pega aquí el JSON devuelto por Gemini.",
                text_color="#aaaaaa"
            )

    def _start_transcribe_thread(self):
        audio = self.app.project_paths.get("audio_file") if self.app.project_paths else None
        if not audio or not os.path.exists(audio):
            messagebox.showwarning("Atención", "El proyecto actual no tiene un archivo de audio válido.")
            return

        self.btn_transcribe.configure(state="disabled", text="Transcribiendo...")
        self.lbl_t1_status.configure(text="Cargando modelo Whisper...", text_color="#ffc107")

        def _worker():
            try:
                text = self.app.aligner.transcribe_to_plain_text(
                    audio,
                    lambda s: self.app.run_on_ui_thread(lambda: self.lbl_t1_status.configure(text=s))
                )
                self.app.run_on_ui_thread(lambda: self._on_transcribe_success(text))
            except Exception as e:
                self.app.run_on_ui_thread(lambda: self._on_transcribe_error(str(e)))
            finally:
                self.app.aligner.unload_model()

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

        lang = self.app.pm.get_project_language(self.app.current_project)
        prompt = self.app.aligner.generate_gemini_prompt(content, target_lang=lang)
        self.clipboard_clear()
        self.clipboard_append(prompt)
        lang_label = "Portugués (Brasil)" if lang == "pt" else "Inglés"
        self.lbl_t1_status.configure(text=f"¡Prompt ({lang_label}) copiado al portapapeles! Pégalo en Gemini Web.", text_color="#28a745")
        messagebox.showinfo("Copiado", f"El prompt formateado para doblaje a {lang_label} fue copiado al portapapeles.\nPégalo en Gemini Web y copia el JSON resultante.")

    def _save_raw_json(self):
        raw = self.txt_json.get("1.0", "end-1c").strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("El JSON debe ser una lista de segmentos [ { ... }, { ... } ]")
            self.app.segments_data = data
            self.app.master_segments = copy.deepcopy(data)
            self.app.pm.save_project_metadata(self.app.current_project, data)
            self.app.pm.save_master_metadata(self.app.current_project, self.app.master_segments)
            if self.app.processor:
                self.app.processor.metadata = data
                self.app.processor.recalculate_end_times()
            self.app.notify_metadata_updated()
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

        audio = self.app.project_paths.get("audio_file") if self.app.project_paths else None
        if not audio or not os.path.exists(audio):
            messagebox.showerror("Error", "No se encontró el audio original del proyecto.")
            return

        self.btn_align.configure(state="disabled", text="Sincronizando...")
        self.lbl_t1_align_status.configure(text="Iniciando alineación por palabras con Whisper...", text_color="#ffc107")

        def _worker():
            try:
                aligned_data, duration_ms = self.app.aligner.align_timestamps(
                    audio,
                    data,
                    lambda s: self.app.run_on_ui_thread(lambda: self.lbl_t1_align_status.configure(text=s))
                )
                self.app.run_on_ui_thread(lambda: self._on_align_success(aligned_data, duration_ms))
            except Exception as e:
                self.app.run_on_ui_thread(lambda: self._on_align_error(str(e)))
            finally:
                self.app.aligner.unload_model()

        gc.collect()
        threading.Thread(target=_worker, daemon=True).start()

    def _on_align_success(self, aligned_data, duration_ms):
        from core.timing_validator import TimingValidator
        self.btn_align.configure(state="normal", text="⏱️ Sincronizar Tiempos (Whisper)")
        self.app.segments_data = aligned_data
        self.app.master_segments = copy.deepcopy(aligned_data)
        self.app.pm.save_project_metadata(self.app.current_project, aligned_data)
        self.app.pm.save_master_metadata(self.app.current_project, self.app.master_segments)
        if self.app.processor:
            self.app.processor.metadata = aligned_data
            self.app.processor.recalculate_end_times()
        self.refresh()
        self.app.notify_metadata_updated()

        val = TimingValidator.validate(aligned_data, duration_ms)
        if val["has_errors"]:
            self.lbl_t1_align_status.configure(text=val["summary_text"], text_color="#ffb74d")
            messagebox.showwarning(
                "Sincronización con Advertencias",
                f"Tiempos sincronizados ({len(aligned_data)} segmentos, {duration_ms} ms analizados).\n\n"
                f"{val['summary_text']}\n\n"
                "Revisa la Pestaña 2 (Doblaje) para inspeccionar los segmentos destacados."
            )
        else:
            self.lbl_t1_align_status.configure(text=val["summary_text"], text_color="#28a745")
            messagebox.showinfo(
                "Éxito",
                f"¡Tiempos sincronizados! {len(aligned_data)} segmentos alineados ({duration_ms} ms analizados).\n"
                "Todos los segmentos están en perfecto orden cronológico."
            )

    def _on_align_error(self, err):
        self.btn_align.configure(state="normal", text="⏱️ Sincronizar Tiempos (Whisper)")
        self.lbl_t1_align_status.configure(text=f"Error en alineación: {err}", text_color="#e57373")
        messagebox.showerror("Error de Alineación", err)
