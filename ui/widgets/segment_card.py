import os
import io
from tkinter import messagebox
import customtkinter as ctk
from pydub import AudioSegment
import pygame

class SegmentCard(ctk.CTkFrame):
    """Tarjeta individual para editar y doblar cada segmento en la Pestaña 2."""

    def __init__(self, master, segment_data, audio_path, audios_dir, save_callback, delete_callback, request_callback, anomalies=None, **kwargs):
        super().__init__(master, **kwargs)
        self.data = segment_data
        self.original_audio_path = audio_path
        self.audios_dir = audios_dir
        self.save_callback = save_callback
        self.delete_callback = delete_callback
        self.request_callback = request_callback
        self.anomalies = anomalies or []

        border_clr = "#e53935" if self.anomalies else "#3d3d3d"
        border_w = 2 if self.anomalies else 1
        self.configure(fg_color="#2b2b2b", border_width=border_w, border_color=border_clr)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ID
        self.lbl_id = ctk.CTkLabel(self, text=f"ID: {self.data.get('id', 'seg')}", font=("Arial", 11, "bold"), text_color="#aaaaaa")
        self.lbl_id.grid(row=0, column=0, padx=10, pady=(8, 0), sticky="nw")

        # Contenido de texto en 2 columnas lado a lado (Español a la izquierda, Traducción a la derecha)
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=5, sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_columnconfigure(1, weight=1)

        # Columna Izquierda: Español (Seleccionable, Copiable y Editable)
        col_orig = ctk.CTkFrame(text_frame, fg_color="transparent")
        col_orig.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        col_orig.grid_columnconfigure(0, weight=1)

        lbl_header_orig = ctk.CTkLabel(col_orig, text="Español (Original):", font=("Arial", 11, "bold"), text_color="#94a3b8")
        lbl_header_orig.pack(anchor="w", pady=(0, 2))

        self.txt_original = ctk.CTkTextbox(col_orig, height=65, font=("Arial", 12), fg_color="#1e1e1e", border_width=1, border_color="#3a3a3a")
        self.txt_original.pack(fill="both", expand=True)
        self.txt_original.insert("1.0", self.data.get('original', ''))

        # Columna Derecha: Traducción (Editable)
        col_trans = ctk.CTkFrame(text_frame, fg_color="transparent")
        col_trans.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        col_trans.grid_columnconfigure(0, weight=1)

        lbl_header_trans = ctk.CTkLabel(col_trans, text="Traducción Doblada:", font=("Arial", 11, "bold"), text_color="#60a5fa")
        lbl_header_trans.pack(anchor="w", pady=(0, 2))

        self.txt_translated = ctk.CTkTextbox(col_trans, height=65, font=("Arial", 12))
        self.txt_translated.pack(fill="both", expand=True)
        self.txt_translated.insert("1.0", self.data.get('translated', ''))

        # Indicador de balance y densidad de palabras: generadas / originales (pct%) | clasificacion
        self.lbl_density = ctk.CTkLabel(text_frame, text="", font=("Arial", 11, "bold"), anchor="w", justify="left")
        self.lbl_density.grid(row=1, column=0, columnspan=2, pady=(4, 0), sticky="w")

        # Advertencia de tiempos si existen anomalías
        if self.anomalies:
            self.lbl_timing_warning = ctk.CTkLabel(
                text_frame,
                text="⚠️ " + " | ".join(self.anomalies),
                font=("Arial", 11, "bold"),
                text_color="#ff5252",
                wraplength=650,
                justify="left"
            )
            self.lbl_timing_warning.grid(row=2, column=0, columnspan=2, pady=(2, 0), sticky="w")
        else:
            self.lbl_timing_warning = None

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
        self.txt_original.bind("<KeyRelease>", lambda *args: self.update_density_metrics())
        self.txt_translated.bind("<KeyRelease>", lambda *args: self.update_density_metrics())
        self.ent_start.bind("<KeyRelease>", lambda *args: self.update_density_metrics())
        self.ent_end.bind("<KeyRelease>", lambda *args: self.update_density_metrics())

        # Botones de acción
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        self.btn_play_orig = ctk.CTkButton(btn_frame, text="▶ Original", width=110, fg_color="#444444", hover_color="#555555", command=self._play_slice)
        self.btn_play_orig.pack(side="left", padx=5)

        self.btn_save = ctk.CTkButton(btn_frame, text="💾 Guardar", width=110, fg_color="#1f538d", command=self._save_changes)
        self.btn_save.pack(side="left", padx=5)

        self.btn_request = ctk.CTkButton(btn_frame, text="✨ Generar este", width=125, fg_color="#7b1fa2", hover_color="#4a148c", command=lambda: self.request_callback(self.data))
        self.btn_request.pack(side="left", padx=5)

        self.btn_copy_prompt = ctk.CTkButton(
            btn_frame, text="📋 Copiar Prompt IA", width=145,
            font=("Arial", 11, "bold"), fg_color="#a21caf", hover_color="#86198f",
            command=self._on_copy_prompt_clicked
        )
        self.btn_copy_prompt.pack(side="left", padx=5)
        self.btn_copy_prompt.pack_forget() # Oculto por defecto

        self.btn_play_gen = ctk.CTkButton(btn_frame, text="🎧 Oír Doblado", width=125, fg_color="#607d8b", hover_color="#455a64", command=self._play_generated)
        self.btn_play_gen.pack(side="left", padx=5)

        self.btn_delete = ctk.CTkButton(btn_frame, text="🗑 Eliminar", width=95, fg_color="#a83232", hover_color="#822727", command=lambda: self.delete_callback(self.data))
        self.btn_delete.pack(side="right", padx=5)

        self.update_density_metrics()
        self.update_status()

    def update_density_metrics(self):
        orig_text = self.txt_original.get("1.0", "end-1c").strip()
        orig_words = len(orig_text.split()) if orig_text else 0

        trans_text = self.txt_translated.get("1.0", "end-1c").strip()
        trans_words = len(trans_text.split()) if trans_text else 0

        if orig_words == 0:
            if trans_words == 0:
                self.lbl_density.configure(text="0 / 0 (0%) | Sin texto", text_color="#aaaaaa")
            else:
                self.lbl_density.configure(text=f"{trans_words} / 0 | Sin original", text_color="#aaaaaa")
            return

        if trans_words == 0:
            self.lbl_density.configure(text=f"0 / {orig_words} (0%) | Sin traducción", text_color="#aaaaaa")
            return

        pct = (trans_words / orig_words) * 100.0

        if pct < 70.0:
            clasif = "Muy corto"
            color = "#e57373"
        elif pct < 90.0:
            clasif = "Corto"
            color = "#ffb74d"
        elif pct <= 110.0:
            clasif = "Bien"
            color = "#81c784"
        elif pct <= 125.0:
            clasif = "Largo"
            color = "#ffb74d"
        else:
            clasif = "Muy largo"
            color = "#e57373"

        slot_dur, audio_dur, gap_s = self._get_silence_metrics()
        silence_text = ""
        if gap_s > 10.0:
            silence_text = f" | 🚨 Silencio crítico: +{gap_s:.1f}s al final"
            color = "#f43f5e"
        elif gap_s >= 4.0:
            silence_text = f" | ⚠️ Silencio largo: +{gap_s:.1f}s al final"
            if color == "#81c784":
                color = "#f97316"

        self.lbl_density.configure(text=f"{trans_words} / {orig_words} ({pct:.0f}%) | {clasif}{silence_text}", text_color=color)

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
            self.data['original'] = self.txt_original.get("1.0", "end-1c").strip()
            self.data['translated'] = self.txt_translated.get("1.0", "end-1c").strip()
            self.data['start_ms'] = int(self.ent_start.get())
            self.data['end_ms'] = int(self.ent_end.get())
            self.data['tone'] = self.opt_tone.get()
            self.save_callback(self.data)
            self.update_density_metrics()
            self.configure(border_color="#38bdf8", border_width=2)
            self.after(1000, self.update_status)
        except ValueError:
            messagebox.showwarning("Atención", "Los tiempos deben ser números enteros en milisegundos.")

    def _get_silence_metrics(self):
        start_ms = self.data.get('start_ms', 0)
        end_ms = self.data.get('end_ms', 0)
        slot_dur = max(0.0, (end_ms - start_ms) / 1000.0)

        filename = self.data.get('filename', '')
        path = os.path.join(self.audios_dir, filename) if self.audios_dir and filename else None
        audio_dur = 0.0
        if path and os.path.isfile(path) and os.path.getsize(path) > 0:
            try:
                audio_dur = len(AudioSegment.from_file(path)) / 1000.0
            except Exception:
                audio_dur = 0.0

        gap_s = max(0.0, slot_dur - audio_dur) if audio_dur > 0 else 0.0
        return slot_dur, audio_dur, gap_s

    def is_generated(self):
        """Comprueba si el audio de este segmento ya existe físicamente en disco y es válido."""
        if not self.audios_dir:
            return False
        filename = self.data.get('filename', '')
        if not filename:
            return False
        path = os.path.join(self.audios_dir, filename)
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def update_status(self):
        """Actualiza la apariencia, el botón de doblado y la visibilidad del botón de prompt de IA."""
        has_audio = self.is_generated()
        if has_audio:
            self.btn_play_gen.configure(state="normal", fg_color="#2e7d32")
            border_clr = "#e53935" if self.anomalies else "#28a745"
            border_w = 2
            self.configure(fg_color="#1b2e1b", border_color=border_clr, border_width=border_w)
        else:
            self.btn_play_gen.configure(state="disabled", fg_color="#455a64")
            border_clr = "#e53935" if self.anomalies else "#3d3d3d"
            border_w = 2 if self.anomalies else 1
            self.configure(fg_color="#2b2b2b", border_color=border_clr, border_width=border_w)

        # Gestionar botón de copiar prompt IA (Visible si silencio crítico > 10s o slot largo con poco texto)
        slot_dur, audio_dur, gap_s = self._get_silence_metrics()
        trans_text = self.txt_translated.get("1.0", "end-1c").strip()
        trans_words = len(trans_text.split()) if trans_text else 0

        show_prompt_btn = (audio_dur > 0 and gap_s > 10.0) or (slot_dur >= 10.0 and trans_words <= (slot_dur * 1.5))
        if show_prompt_btn:
            self.btn_copy_prompt.pack(side="left", padx=5, after=self.btn_request)
        else:
            self.btn_copy_prompt.pack_forget()

        self.update_density_metrics()

    def _on_copy_prompt_clicked(self):
        slot_dur, audio_dur, gap_s = self._get_silence_metrics()
        orig_text = self.txt_original.get("1.0", "end-1c").strip()
        trans_text = self.txt_translated.get("1.0", "end-1c").strip()
        orig_words = len(orig_text.split()) if orig_text else 0
        trans_words = len(trans_text.split()) if trans_text else 0
        target_words = max(int(slot_dur * 2.3), trans_words + 15)

        prompt = f"""Actúa como un traductor y adaptador de guiones para doblaje audiovisual profesional.
Necesito expandir la siguiente frase en inglés porque en la locución original el orador habla durante mucho más tiempo y la traducción actual deja un silencio incómodo de {gap_s:.1f} segundos.

DATOS DEL SEGMENTO:
- Duración total del espacio en video: {slot_dur:.1f} segundos.
- Duración de la locución actual en inglés: {audio_dur:.1f} segundos.
- Silencio muerto restante: {gap_s:.1f} segundos.
- Palabras en español original: {orig_words} palabras.
- Palabras actuales en inglés: {trans_words} palabras.
- Palabras objetivo sugeridas en inglés: ~{target_words} palabras (~2.3 palabras/segundo).

TEXTO ORIGINAL EN ESPAÑOL:
"{orig_text}"

TRADUCCIÓN ACTUAL (DEMASIADO CORTA):
"{trans_text}"

INSTRUCCIÓN:
Reescribe y expande la traducción en inglés para que alcance aproximadamente {target_words} palabras, explicando la idea con mayor detalle, agregando contexto natural, conectores fluidos o aclaraciones que mantengan intacto el sentido del orador original. Responde ÚNICAMENTE con el texto en inglés resultante, sin explicaciones ni notas."""

        try:
            self.clipboard_clear()
            self.clipboard_append(prompt)
            self.update() # Forzar actualización del portapapeles en Windows
        except Exception:
            pass

        self.btn_copy_prompt.configure(text="✅ ¡Prompt Copiado!", fg_color="#28a745")
        self.after(2500, lambda: self.btn_copy_prompt.configure(text="📋 Copiar Prompt IA", fg_color="#a21caf"))

    def set_processing(self):
        self.configure(border_color="#ffc107", border_width=2)

    def set_done(self):
        self.update_status()
