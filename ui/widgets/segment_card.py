import os
import io
from tkinter import messagebox
import customtkinter as ctk
from pydub import AudioSegment
import pygame

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

        # Indicador de balance y densidad de palabras: generadas / originales (pct%) | clasificacion
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
        orig_text = self.data.get('original', '').strip()
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

        if pct < 55.0:
            clasif = "Muy corto"
            color = "#e57373"
        elif pct < 75.0:
            clasif = "Corto"
            color = "#ffb74d"
        elif pct <= 105.0:
            clasif = "Bien"
            color = "#81c784"
        elif pct <= 125.0:
            clasif = "Largo"
            color = "#ffb74d"
        else:
            clasif = "Muy largo"
            color = "#e57373"

        self.lbl_density.configure(text=f"{trans_words} / {orig_words} ({pct:.0f}%) | {clasif}", text_color=color)

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
