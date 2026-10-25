import threading
import os
import re
import math
import copy
from tkinter import filedialog, messagebox
import customtkinter as ctk
from pydub import AudioSegment

from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_tools import TimelineController
from ui.widgets.segment_row import SegmentRow
from core.export_service import ExportService

class TabStudioView(ctk.CTkFrame):
    """Pestaña 3: Estudio de Mezcla, Timeline interactivo, Ajuste fino y Exportación."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app

        # Variables de estado de audio
        self.total_duration_ms = 1
        self.mute_original = False
        self.mute_dubbed = False
        self.is_dragging = False
        self.segment_rows = {}

        # Variables de Zoom y Scroll Horizontal
        self.zoom_level = 1.0
        self.view_offset_ms = 0.0

        self._build_ui()
        self._init_timeline_controller()
        self._bind_shortcuts()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)  # Contenedor desplazable principal
        self.grid_rowconfigure(1, weight=0)  # Barra inferior fija (Play, Export, etc.)
        self.grid_columnconfigure(0, weight=1)

        # --- CONTENEDOR DESPLAZABLE PRINCIPAL ---
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))
        self.main_scroll.grid_columnconfigure(0, weight=1)
        self.main_scroll._parent_canvas.configure(yscrollincrement=20)

        # 1. ZONA SUPERIOR: FORMAS DE ONDA ALTAS
        wave_frame = ctk.CTkFrame(self.main_scroll)
        wave_frame.pack(fill="x", padx=6, pady=4)
        wave_frame.grid_columnconfigure(0, weight=1)

        # 1. Pista Original
        orig_box = ctk.CTkFrame(wave_frame)
        orig_box.pack(fill="x", padx=5, pady=4)

        orig_header = ctk.CTkFrame(orig_box, fg_color="transparent")
        orig_header.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(orig_header, text="Pista Original", font=("Arial", 12, "bold")).pack(side="left")

        # Altura de onda reducida un 30% (de 290 a 200)
        self.orig_canvas_frame = ctk.CTkFrame(orig_box, height=200)
        self.orig_canvas_frame.pack(fill="x", expand=True, padx=5, pady=2)
        self.orig_canvas = TimelineCanvas(self.orig_canvas_frame, is_dubbed=False)

        # Controles de Mute y Volumen situados DEBAJO de la onda original
        orig_footer = ctk.CTkFrame(orig_box, height=28, fg_color="#181818", corner_radius=4)
        orig_footer.pack(fill="x", padx=5, pady=(1, 3))

        self.btn_mute_orig = ctk.CTkButton(orig_footer, text="Mute", width=55, height=22, command=self._toggle_mute_orig)
        self.btn_mute_orig.pack(side="left", padx=(8, 4), pady=2)

        ctk.CTkLabel(orig_footer, text="Vol:", font=("Arial", 11), text_color="#aaaaaa").pack(side="left", padx=(2, 2))
        self.slider_vol_orig = ctk.CTkSlider(orig_footer, from_=0, to=2, width=120)
        self.slider_vol_orig.set(1.0)
        self.slider_vol_orig.pack(side="left", padx=(2, 12), pady=2)

        self.lbl_orig_hover = ctk.CTkLabel(
            orig_footer,
            text="Pasa el cursor sobre la onda para inspeccionar el texto...",
            font=("Arial", 11),
            text_color="#64748b",
            anchor="w"
        )
        self.lbl_orig_hover.pack(side="left", padx=5, fill="x", expand=True)

        # 2. Pista Doblada
        dub_box = ctk.CTkFrame(wave_frame)
        dub_box.pack(fill="x", padx=5, pady=4)

        dub_header = ctk.CTkFrame(dub_box, fg_color="transparent")
        dub_header.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(dub_header, text="Pista Doblada", font=("Arial", 12, "bold")).pack(side="left")
        self.btn_mute_dub = ctk.CTkButton(dub_header, text="Mute", width=55, height=24, command=self._toggle_mute_dub)
        self.btn_mute_dub.pack(side="left", padx=8)
        self.slider_vol_dub = ctk.CTkSlider(dub_header, from_=0, to=2, width=100)
        self.slider_vol_dub.set(1.0)
        self.slider_vol_dub.pack(side="left", padx=4)

        # Herramientas de edición
        self.btn_tool_select = ctk.CTkButton(
            dub_header, text="↖️ Selección", width=95, height=24,
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

        self.btn_delete_seg = ctk.CTkButton(
            dub_header, text="🗑️ Suprimir", width=78, height=24,
            fg_color="#2b2b2b", hover_color="#822727", state="disabled",
            command=self._delete_selected_segment
        )
        self.btn_delete_seg.pack(side="left", padx=2)

        self.btn_auto_split_top = ctk.CTkButton(
            dub_header, text="🧩 Auto-dividir", width=115, height=24,
            fg_color="#2b2b2b", hover_color="#0284c7", state="disabled",
            command=self._auto_split_selected_segment
        )
        self.btn_auto_split_top.pack(side="left", padx=2)

        self.btn_auto_split_all = ctk.CTkButton(
            dub_header, text="⚡ Auto-dividir Todos", width=145, height=24,
            fg_color="#0284c7", hover_color="#0369a1",
            command=self._auto_split_all_action
        )
        self.btn_auto_split_all.pack(side="left", padx=2)

        self.btn_reset_dub = ctk.CTkButton(
            dub_header, text="↺ Resetear a Original", width=145, height=24,
            fg_color="#a83232", hover_color="#822727",
            command=self._reset_dubbed_positions
        )
        self.btn_reset_dub.pack(side="right", padx=10)

        # Altura de onda reducida un 30% (de 290 a 200)
        self.dub_canvas_frame = ctk.CTkFrame(dub_box, height=200)
        self.dub_canvas_frame.pack(fill="x", expand=True, padx=5, pady=2)
        self.dub_canvas = TimelineCanvas(self.dub_canvas_frame, is_dubbed=True)

        dub_footer = ctk.CTkFrame(dub_box, height=26, fg_color="#181818", corner_radius=4)
        dub_footer.pack(fill="x", padx=5, pady=(1, 3))
        self.lbl_dub_hover = ctk.CTkLabel(
            dub_footer,
            text="Pasa el cursor sobre la onda doblada para inspeccionar el texto...",
            font=("Arial", 11),
            text_color="#64748b",
            anchor="w"
        )
        self.lbl_dub_hover.pack(side="left", padx=10, fill="x", expand=True)

        # 3. Barra de Navegación y Zoom Horizontal
        zoom_nav_frame = ctk.CTkFrame(wave_frame, height=36, fg_color="#181818", corner_radius=6)
        zoom_nav_frame.pack(fill="x", padx=5, pady=(2, 6))
        zoom_nav_frame.grid_columnconfigure(3, weight=1)

        self.btn_zoom_out = ctk.CTkButton(
            zoom_nav_frame, text="➖", width=32, height=26, font=("Arial", 12, "bold"),
            fg_color="#2b2b2b", hover_color="#3d3d3d", command=self._on_zoom_out
        )
        self.btn_zoom_out.grid(row=0, column=0, padx=(8, 2), pady=4)

        self.lbl_zoom = ctk.CTkLabel(
            zoom_nav_frame, text="🔍 1.0x", width=62, font=("Consolas", 12, "bold"), text_color="#38bdf8"
        )
        self.lbl_zoom.grid(row=0, column=1, padx=2, pady=4)

        self.btn_zoom_in = ctk.CTkButton(
            zoom_nav_frame, text="➕", width=32, height=26, font=("Arial", 12, "bold"),
            fg_color="#2b2b2b", hover_color="#3d3d3d", command=self._on_zoom_in
        )
        self.btn_zoom_in.grid(row=0, column=2, padx=(2, 10), pady=4)

        self.h_scrollbar = ctk.CTkSlider(
            zoom_nav_frame, from_=0, to=100, command=self._on_h_scroll, height=16
        )
        self.h_scrollbar.set(0)
        self.h_scrollbar.grid(row=0, column=3, sticky="ew", padx=10, pady=4)

        self.btn_zoom_fit = ctk.CTkButton(
            zoom_nav_frame, text="Ajustar 1:1", width=85, height=26,
            fg_color="#2b2b2b", hover_color="#3d3d3d", command=self._on_zoom_fit
        )
        self.btn_zoom_fit.grid(row=0, column=4, padx=(5, 10), pady=4)

        # --- ZONA MEDIA: BARRA DE PROGRESO / SEEK ---
        seek_frame = ctk.CTkFrame(self.main_scroll)
        seek_frame.pack(fill="x", padx=6, pady=6)

        self.seek_slider = ctk.CTkSlider(seek_frame, from_=0, to=100, command=self._on_seek_change)
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self.seek_slider.bind("<ButtonPress-1>", lambda e: setattr(self, 'is_dragging', True))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)

        self.lbl_time = ctk.CTkLabel(seek_frame, text="0 ms / 0 ms", width=150, font=("Consolas", 12, "bold"))
        self.lbl_time.pack(side="right", padx=10)

        # --- ZONA INFERIOR: AJUSTE FINO DE SEGMENTOS ---
        mid_header = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        mid_header.pack(fill="x", padx=10, pady=(12, 4))
        ctk.CTkLabel(mid_header, text="⚙️ Ajuste Fino de Segmentos", font=("Arial", 14, "bold"), text_color="#cbd5e1").pack(side="left")

        self.mid_scroll = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.mid_scroll.pack(fill="x", padx=6, pady=(0, 20))

        # --- BARRA FIJA INFERIOR: BOTONES GLOBALES Y EXPORTACIÓN ---
        bot_frame = ctk.CTkFrame(self)
        bot_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=8)

        self.btn_play_mix = ctk.CTkButton(
            bot_frame, text="▶ Reproducir Mezcla", font=("Arial", 14, "bold"),
            fg_color="#007bff", hover_color="#0056b3",
            command=self._toggle_play_global
        )
        self.btn_play_mix.pack(side="left", padx=10, pady=10)

        btn_apply_times = ctk.CTkButton(
            bot_frame, text="Aplicar Tiempos", fg_color="#ffc107", text_color="black", hover_color="#d39e00",
            command=self._apply_timing_changes
        )
        btn_apply_times.pack(side="left", padx=5)

        btn_reload_studio = ctk.CTkButton(bot_frame, text="🔄 Recargar Mezcla", width=120, command=self.refresh)
        btn_reload_studio.pack(side="left", padx=5)

        self.btn_auto_split_bottom = ctk.CTkButton(
            bot_frame, text="🧩 Auto-dividir Silencio", font=("Arial", 13, "bold"),
            fg_color="#2b2b2b", hover_color="#0284c7", state="disabled",
            command=self._auto_split_selected_segment
        )
        self.btn_auto_split_bottom.pack(side="left", padx=5)

        self.btn_auto_split_all_bottom = ctk.CTkButton(
            bot_frame, text="⚡ Auto-dividir Todos", font=("Arial", 13, "bold"),
            fg_color="#0284c7", hover_color="#0369a1",
            command=self._auto_split_all_action
        )
        self.btn_auto_split_all_bottom.pack(side="left", padx=5)

        # Exportar
        self.btn_export_video = ctk.CTkButton(
            bot_frame, text="🎬 Exportar Video Doblado", fg_color="#6f42c1", hover_color="#59359a",
            command=self._export_video
        )
        self.btn_export_video.pack(side="right", padx=(5, 10), pady=10)

        self.btn_export_audio = ctk.CTkButton(
            bot_frame, text="💾 Exportar Audio Doblado", font=("Arial", 13, "bold"), fg_color="#28a745", hover_color="#218838",
            command=self._export_audio
        )
        self.btn_export_audio.pack(side="right", padx=5, pady=10)

    def _init_timeline_controller(self):
        callbacks = {
            "on_selection_changed": self._on_selection_changed,
            "on_metadata_modified": self._on_metadata_modified,
            "on_seek": self._on_seek_from_click,
            "on_hover_orig": lambda txt, clr: self.lbl_orig_hover.configure(text=txt, text_color=clr),
            "on_hover_dub": lambda txt, clr: self.lbl_dub_hover.configure(text=txt, text_color=clr),
            "on_time_label_update": lambda txt: self.lbl_time.configure(text=txt),
        }
        self.timeline_ctrl = TimelineController(
            get_processor=lambda: self.app.processor,
            get_project_paths=lambda: self.app.project_paths,
            get_master_segments=lambda: self.app.master_segments,
            get_total_duration_ms=lambda: self.total_duration_ms,
            dub_canvas_comp=self.dub_canvas,
            orig_canvas_comp=self.orig_canvas,
            callbacks=callbacks
        )

    def _bind_shortcuts(self):
        self.app.bind("<Delete>", lambda e: self._on_key_delete())
        self.app.bind("<BackSpace>", lambda e: self._on_key_delete())
        self.app.bind("<c>", lambda e: self._on_key_shortcut(e))
        self.app.bind("<C>", lambda e: self._on_key_shortcut(e))
        self.app.bind("<v>", lambda e: self._on_key_shortcut(e))
        self.app.bind("<V>", lambda e: self._on_key_shortcut(e))

    def _on_key_delete(self):
        focus_w = self.app.focus_get()
        if focus_w and hasattr(focus_w, 'winfo_class') and focus_w.winfo_class() in ('Entry', 'Text', 'CTkEntry', 'CTkTextbox'):
            return
        if self.timeline_ctrl.selected_segment_id:
            self._delete_selected_segment()

    def _on_key_shortcut(self, event):
        focus_w = self.app.focus_get()
        if focus_w and hasattr(focus_w, 'winfo_class') and focus_w.winfo_class() in ('Entry', 'Text', 'CTkEntry', 'CTkTextbox'):
            return
        if event.char in ('c', 'C'):
            self._set_tool_mode("RAZOR")
        elif event.char in ('v', 'V'):
            self._set_tool_mode("SELECT")

    def _set_tool_mode(self, mode):
        self.timeline_ctrl.set_tool_mode(mode)
        if mode == "SELECT":
            self.btn_tool_select.configure(fg_color="#1f6aa5")
            self.btn_tool_razor.configure(fg_color="#333333")
        elif mode == "RAZOR":
            self.btn_tool_select.configure(fg_color="#333333")
            self.btn_tool_razor.configure(fg_color="#c62828")

    def _on_selection_changed(self, seg_id):
        self._update_delete_button_state()
        for sid, row in self.segment_rows.items():
            row.set_selected(sid == seg_id)
        # Resaltado instantáneo sin re-mezclar audio ni reconstruir la figura completa (< 1ms)
        self.dub_canvas.highlight_selected_segment(seg_id)

    def _on_metadata_modified(self):
        if self.app.processor:
            self.app.processor.mark_mix_dirty()
            self.app.processor.recalculate_end_times()
            self.app.pm.save_project_metadata(self.app.current_project, self.app.processor.metadata)
        self.refresh()
        self.app.notify_metadata_updated()

    def _delete_selected_segment(self):
        self.timeline_ctrl.delete_selected_segment()

    def _can_auto_split(self, seg_id):
        if not seg_id or not self.app.processor or not self.app.processor.metadata:
            return False

        # 1. Comprobar en current_silences usando comparación segura de str
        silences = getattr(self.timeline_ctrl, "current_silences", []) or getattr(self.timeline_ctrl, "silences", [])
        for sil in silences:
            if str(sil[2]) == str(seg_id) and sil[3] >= 4.0:
                return True

        # 2. Comprobar directamente en metadatos y archivo de audio en disco por robustez
        seg = next((s for s in self.app.processor.metadata if str(s.get('id')) == str(seg_id)), None)
        if not seg:
            return False

        start_ms = seg.get('start_ms', 0)
        end_ms = seg.get('end_ms', 0)
        slot_span = end_ms - start_ms
        if slot_span < 4000:
            return False

        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None
        fname = seg.get('filename', '')
        if audios_dir and fname:
            fpath = os.path.join(audios_dir, fname)
            if os.path.isfile(fpath):
                try:
                    from pydub import AudioSegment
                    audio_dur = len(AudioSegment.from_file(fpath))
                    gap_ms = slot_span - audio_dur
                    if gap_ms >= 4000:
                        return True
                except Exception:
                    pass

        return False

    def _update_delete_button_state(self):
        seg_id = self.timeline_ctrl.selected_segment_id
        if seg_id:
            self.btn_delete_seg.configure(state="normal", fg_color="#c62828")
        else:
            self.btn_delete_seg.configure(state="disabled", fg_color="#2b2b2b")

        can_split = self._can_auto_split(seg_id)
        if can_split:
            self.btn_auto_split_top.configure(state="normal", fg_color="#0284c7")
            self.btn_auto_split_bottom.configure(state="normal", fg_color="#0284c7")
        else:
            self.btn_auto_split_top.configure(state="disabled", fg_color="#2b2b2b")
            self.btn_auto_split_bottom.configure(state="disabled", fg_color="#2b2b2b")

    def _find_best_split_point(self, text):
        if not text or len(text) < 10:
            return None
        # 1. Puntuación sintáctica: comas, punto y coma, dos puntos
        delimiters = [",", ";", ":"]
        candidates = [i for i, ch in enumerate(text) if ch in delimiters and 4 < i < (len(text) - 4)]
        if candidates:
            mid = len(text) / 2.0
            best_idx = min(candidates, key=lambda i: abs(i - mid))
            return best_idx + 1

        # 2. Conjunciones comunes de transición
        conjunctions = [" and ", " but ", " so ", " because ", " which ", " while ", " although ", " that "]
        found = []
        lower = text.lower()
        for c in conjunctions:
            pos = 0
            while True:
                idx = lower.find(c, pos)
                if idx == -1:
                    break
                if 4 < idx < (len(text) - 4):
                    found.append(idx + 1)
                pos = idx + len(c)
        if found:
            mid = len(text) / 2.0
            return min(found, key=lambda i: abs(i - mid))

        return None

    def _find_acoustic_split_point(self, audio, approx_cut_ms, window_ms=600):
        """Encuentra el punto de menor energía (silencio/respiración) cerca de la coma."""
        total_len = len(audio)
        if total_len <= 100:
            return max(1, total_len // 2)

        start_search = max(50, approx_cut_ms - window_ms)
        end_search = min(total_len - 50, approx_cut_ms + window_ms)

        if start_search >= end_search:
            return max(1, min(total_len - 1, approx_cut_ms))

        best_ms = approx_cut_ms
        min_rms = float('inf')
        step = 25

        for t in range(start_search, end_search, step):
            chunk = audio[t : min(total_len, t + 40)]
            rms = chunk.rms
            if rms < min_rms:
                min_rms = rms
                best_ms = t

        return max(1, min(total_len - 1, best_ms))

    def _auto_split_selected_segment(self):
        seg_id = self.timeline_ctrl.selected_segment_id
        if not seg_id or not self.app.processor or not self.app.processor.metadata:
            return

        seg = next((s for s in self.app.processor.metadata if str(s.get('id')) == str(seg_id)), None)
        if not seg:
            return

        text_en = seg.get('translated', '').strip()
        text_es = seg.get('original', '').strip()

        # 1. Buscar corte sintáctico en inglés
        split_idx_en = self._find_best_split_point(text_en)
        if split_idx_en is None:
            messagebox.showinfo(
                "No se puede auto-dividir",
                "El texto en inglés de este segmento no contiene comas ni conjunciones naturales para dividirlo de forma segura."
            )
            return

        part1_en = text_en[:split_idx_en].strip()
        part2_en = text_en[split_idx_en:].lstrip(",:; ").strip()

        # En español intentamos dividir por puntuación o por mitad de palabras
        split_idx_es = self._find_best_split_point(text_es)
        if split_idx_es is not None:
            part1_es = text_es[:split_idx_es].strip()
            part2_es = text_es[split_idx_es:].lstrip(",:; ").strip()
        else:
            words_es = text_es.split()
            half_w = max(1, len(words_es) // 2)
            part1_es = " ".join(words_es[:half_w])
            part2_es = " ".join(words_es[half_w:])

        # 2. Cargar audio existente y realizar corte acústico real
        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None
        fname = seg.get('filename', '')
        fpath = os.path.join(audios_dir, fname) if audios_dir and fname else None

        if not fpath or not os.path.isfile(fpath):
            messagebox.showwarning(
                "Audio no encontrado",
                f"No se encontró el archivo de audio '{fname}' en disco.\nGenera primero el audio en la pestaña de Doblaje."
            )
            return

        try:
            full_audio = AudioSegment.from_file(fpath)
        except Exception as e:
            messagebox.showerror("Error al cargar audio", f"No se pudo leer el archivo de audio: {e}")
            return

        total_audio_len = len(full_audio)
        if total_audio_len <= 50:
            messagebox.showwarning("Audio muy corto", "El audio de este segmento es demasiado breve para ser dividido.")
            return

        words_p1 = max(1, len(part1_en.split()))
        words_p2 = max(1, len(part2_en.split()))
        words_ratio = words_p1 / (words_p1 + words_p2)

        approx_cut_ms = int(total_audio_len * words_ratio)
        acoustic_cut_ms = self._find_acoustic_split_point(full_audio, approx_cut_ms, window_ms=600)

        part1_audio = full_audio[:acoustic_cut_ms]
        part2_audio = full_audio[acoustic_cut_ms:]

        dur_1 = len(part1_audio)
        dur_2 = len(part2_audio)

        # 3. Nombres y rutas para los nuevos archivos de audio
        base_name = os.path.splitext(fname)[0]
        clean_base = re.sub(r'_[ab]$', '', base_name)
        name_a = f"{clean_base}_a.wav"
        name_b = f"{clean_base}_b.wav"
        path_a = os.path.join(audios_dir, name_a)
        path_b = os.path.join(audios_dir, name_b)

        # Exportar archivos físicos
        try:
            part1_audio.export(path_a, format="wav")
            part2_audio.export(path_b, format="wav")
        except Exception as e:
            messagebox.showerror("Error al exportar", f"Fallo al guardar los fragmentos de audio cortados: {e}")
            return

        # Registrar en el caché de audio en memoria
        self.app.processor.processed_segments[name_a] = part1_audio
        self.app.processor.processed_segments[name_b] = part2_audio

        # 4. Cálculo de tiempos y reparto equitativo del silencio (50% en medio y 50% al final)
        start_ms = seg.get('start_ms', 0)
        end_ms = seg.get('end_ms', 0)
        total_span = end_ms - start_ms

        dead_air = max(0, total_span - (dur_1 + dur_2))
        pause_mid = dead_air // 2
        pause_end = dead_air - pause_mid

        # Frase A: Inicia en start_ms y termina exactamente al terminar su voz (ratio = 1.00x)
        start_1 = start_ms
        end_1 = start_1 + dur_1

        # Frase B: Inicia tras la pausa intermedia y termina en end_ms
        start_2 = end_1 + pause_mid
        end_2 = end_ms

        # 5. Generar IDs únicos y actualizar metadatos
        clean_seg_id = re.sub(r'_[ab]$', '', str(seg_id))
        id_a = f"{clean_seg_id}_a"
        id_b = f"{clean_seg_id}_b"

        idx = self.app.processor.metadata.index(seg)

        seg_a = copy.deepcopy(seg)
        seg_a['id'] = id_a
        seg_a['filename'] = name_a
        seg_a['translated'] = part1_en
        seg_a['original'] = part1_es
        seg_a['start_ms'] = start_1
        seg_a['end_ms'] = end_1

        seg_b = copy.deepcopy(seg)
        seg_b['id'] = id_b
        seg_b['filename'] = name_b
        seg_b['translated'] = part2_en
        seg_b['original'] = part2_es
        seg_b['start_ms'] = start_2
        seg_b['end_ms'] = end_2

        self.app.processor.metadata[idx] = seg_a
        self.app.processor.metadata.insert(idx + 1, seg_b)

        # Invalida la caché de mezcla y refresca la UI
        self._on_metadata_modified()

        # Seleccionar la primera parte para mantener feedback visual activo
        self.timeline_ctrl.selected_segment_id = id_a
        self._update_delete_button_state()
        self.dub_canvas.highlight_selected_segment(id_a)

        messagebox.showinfo(
            "Auto-División Exitosa",
            f"El segmento [{seg_id}] fue dividido físicamente en 2 frases y 2 audios:\n\n"
            f"• Frase A [{id_a}] ({dur_1/1000.0:.1f}s): {start_1} ms a {end_1} ms (Velocidad natural 1.00x)\n"
            f"• Pausa intermedia: {pause_mid / 1000.0:.1f}s\n"
            f"• Frase B [{id_b}] ({dur_2/1000.0:.1f}s): {start_2} ms a {end_2} ms (Velocidad natural 1.00x)\n"
            f"• Silencio final: {pause_end / 1000.0:.1f}s\n\n"
            "El audio ha sido cortado y sincronizado al instante en la línea de tiempo."
        )

    def _get_auto_split_candidates(self):
        """Devuelve los segmentos que califican para auto-división masiva (silencio >= 4s y con comas)."""
        processor = self.app.processor
        if not processor or not processor.metadata:
            return []

        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None
        if not audios_dir or not os.path.exists(audios_dir):
            return []

        candidates = []
        for seg in processor.metadata:
            start_ms = seg.get('start_ms', 0)
            end_ms = seg.get('end_ms', 0)
            slot_span = end_ms - start_ms
            if slot_span < 4000:
                continue

            fname = seg.get('filename', '')
            fpath = os.path.join(audios_dir, fname) if fname else None
            if not fpath or not os.path.isfile(fpath) or os.path.getsize(fpath) == 0:
                continue

            try:
                audio_len = len(AudioSegment.from_file(fpath))
            except Exception:
                continue

            dead_air = slot_span - audio_len
            if dead_air < 4000:
                continue

            text_en = seg.get('translated', '').strip()
            if self._find_best_split_point(text_en) is None:
                continue

            candidates.append((seg, fpath, audio_len, dead_air))

        return candidates

    def _auto_split_all_action(self):
        candidates = self._get_auto_split_candidates()
        if not candidates:
            messagebox.showinfo(
                "Sin segmentos para dividir",
                "No se encontraron segmentos con silencios >= 4.0s que contengan comas o conjunciones para auto-dividir."
            )
            return

        n = len(candidates)
        resp = messagebox.askyesno(
            "Confirmar Auto-División Masiva",
            f"Se encontraron {n} segmentos con silencios largos (>= 4.0s) listos para auto-dividir.\n\n"
            "El proceso cortará físicamente los archivos de audio y repartirá el silencio muerto equitativamente "
            "(50% en medio y 50% al final) a velocidad natural 1.00x.\n\n"
            f"¿Deseas procesar los {n} segmentos automáticamente?"
        )
        if not resp:
            return

        self.btn_auto_split_all.configure(state="disabled", text="⚡ Procesando...")
        self.btn_auto_split_all_bottom.configure(state="disabled", text="⚡ Procesando...")

        def _worker():
            audios_dir = self.app.project_paths.get("audios_dir")
            completed_count = 0

            for idx, (seg, fpath, audio_len, dead_air) in enumerate(candidates):
                seg_id = seg.get('id')
                self.app.run_on_ui_thread(
                    lambda i=idx+1, sid=seg_id: self.lbl_dub_hover.configure(
                        text=f"⚡ Auto-dividiendo {i} de {n} [{sid}]...",
                        text_color="#38bdf8"
                    )
                )

                try:
                    # 1. División sintáctica de texto
                    text_en = seg.get('translated', '').strip()
                    text_es = seg.get('original', '').strip()
                    split_idx_en = self._find_best_split_point(text_en)
                    part1_en = text_en[:split_idx_en].strip()
                    part2_en = text_en[split_idx_en:].lstrip(",:; ").strip()

                    split_idx_es = self._find_best_split_point(text_es)
                    if split_idx_es is not None:
                        part1_es = text_es[:split_idx_es].strip()
                        part2_es = text_es[split_idx_es:].lstrip(",:; ").strip()
                    else:
                        words_es = text_es.split()
                        hw = max(1, len(words_es) // 2)
                        part1_es = " ".join(words_es[:hw])
                        part2_es = " ".join(words_es[hw:])

                    # 2. Corte acústico
                    full_audio = AudioSegment.from_file(fpath)
                    w1 = max(1, len(part1_en.split()))
                    w2 = max(1, len(part2_en.split()))
                    approx_cut = int(audio_len * (w1 / (w1 + w2)))
                    acoustic_cut = self._find_acoustic_split_point(full_audio, approx_cut, window_ms=600)

                    part1_audio = full_audio[:acoustic_cut]
                    part2_audio = full_audio[acoustic_cut:]
                    dur_1 = len(part1_audio)
                    dur_2 = len(part2_audio)

                    # 3. Exportar archivos WAV físicos
                    fname = seg.get('filename', '')
                    base_name = os.path.splitext(fname)[0]
                    clean_base = re.sub(r'_[ab]$', '', base_name)
                    name_a = f"{clean_base}_a.wav"
                    name_b = f"{clean_base}_b.wav"
                    part1_audio.export(os.path.join(audios_dir, name_a), format="wav")
                    part2_audio.export(os.path.join(audios_dir, name_b), format="wav")

                    self.app.processor.processed_segments[name_a] = part1_audio
                    self.app.processor.processed_segments[name_b] = part2_audio

                    # 4. Cálculo de tiempos y reparto 50/50
                    start_ms = seg.get('start_ms', 0)
                    end_ms = seg.get('end_ms', 0)
                    tot_span = end_ms - start_ms
                    actual_dead_air = max(0, tot_span - (dur_1 + dur_2))
                    pause_mid = actual_dead_air // 2

                    start_1 = start_ms
                    end_1 = start_1 + dur_1
                    start_2 = end_1 + pause_mid
                    end_2 = end_ms

                    # 5. Sustituir en metadatos
                    clean_id = re.sub(r'_[ab]$', '', str(seg_id))
                    seg_a = copy.deepcopy(seg)
                    seg_a['id'] = f"{clean_id}_a"
                    seg_a['filename'] = name_a
                    seg_a['translated'] = part1_en
                    seg_a['original'] = part1_es
                    seg_a['start_ms'] = start_1
                    seg_a['end_ms'] = end_1

                    seg_b = copy.deepcopy(seg)
                    seg_b['id'] = f"{clean_id}_b"
                    seg_b['filename'] = name_b
                    seg_b['translated'] = part2_en
                    seg_b['original'] = part2_es
                    seg_b['start_ms'] = start_2
                    seg_b['end_ms'] = end_2

                    cur_idx = next((i for i, s in enumerate(self.app.processor.metadata) if str(s.get('id')) == str(seg_id)), None)
                    if cur_idx is None:
                        continue
                    self.app.processor.metadata[cur_idx] = seg_a
                    self.app.processor.metadata.insert(cur_idx + 1, seg_b)

                    completed_count += 1
                except Exception as e:
                    print(f"[ERROR Auto-split all] Fallo en segmento {seg.get('id')}: {e}")

            def _finish_ui():
                self.btn_auto_split_all.configure(state="normal", text="⚡ Auto-dividir Todos")
                self.btn_auto_split_all_bottom.configure(state="normal", text="⚡ Auto-dividir Todos")
                # Guardado de metadata y refresco único consolidado (rápido y fluido)
                self._on_metadata_modified()
                messagebox.showinfo(
                    "Auto-División Masiva Completada",
                    f"¡Se auto-dividieron {completed_count} de {n} segmentos exitosamente!\n\n"
                    "Todos los audios fueron cortados acústicamente y sincronizados a velocidad 1.00x "
                    "con el silencio muerto repartido equitativamente (50% en medio y 50% al final)."
                )

            self.app.run_on_ui_thread(_finish_ui)

        threading.Thread(target=_worker, daemon=True).start()

    def refresh(self):
        for w in self.mid_scroll.winfo_children():
            w.destroy()
        self.segment_rows.clear()
        self._update_delete_button_state()

        if not self.app.processor or not self.app.processor.original_audio:
            return

        for seg in self.app.processor.metadata:
            try:
                _, ratio = self.app.processor.process_segment(seg)
                is_sel = (self.timeline_ctrl.selected_segment_id == seg.get("id"))
                row = SegmentRow(
                    self.mid_scroll,
                    seg,
                    ratio,
                    on_play_callback=self._toggle_play_segment_slice,
                    on_select_callback=self._select_segment_from_row,
                    on_adjust_callback=self._regenerate_segment,
                    is_selected=is_sel
                )
                row.pack(fill="x", pady=3, padx=5)
                self.segment_rows[seg["id"]] = row
            except Exception as e:
                print(f"[WARN] Error procesando segmento {seg.get('filename')}: {e}")

        self._update_waveforms()

        has_video = bool(self.app.project_paths.get("video_file") and os.path.exists(self.app.project_paths["video_file"]))
        self.btn_export_video.configure(state="normal" if has_video else "disabled")

    def _select_segment_from_row(self, segment):
        self.timeline_ctrl.selected_segment_id = segment.get("id")
        self._on_selection_changed(self.timeline_ctrl.selected_segment_id)

    def _regenerate_segment(self, segment, entry_widget):
        try:
            r = float(entry_widget.get().strip())
            self.app.processor.process_segment(segment, manual_ratio=r)
            self._update_waveforms()
            messagebox.showinfo("Éxito", f"Segmento {segment.get('filename')} recalculado con ratio {r:.2f}.")
        except Exception as e:
            messagebox.showerror("Error", f"Ratio inválido o error al procesar: {e}")

    def _apply_timing_changes(self):
        if not self.app.processor:
            return
        try:
            for seg in self.app.processor.metadata:
                sid = seg.get("id")
                if sid in self.segment_rows:
                    seg["start_ms"] = max(0, self.segment_rows[sid].get_start_ms())

            self.app.processor.recalculate_end_times()
            self.app.pm.save_project_metadata(self.app.current_project, self.app.processor.metadata)
            self.refresh()
            self.app.notify_metadata_updated()
            messagebox.showinfo("Éxito", "Tiempos actualizados y proyecto recalculado.")
        except ValueError:
            messagebox.showerror("Error", "Los tiempos de inicio deben ser números enteros válidos.")

    def _reset_dubbed_positions(self):
        if not self.app.processor:
            return
        source = self.app.master_segments if self.app.master_segments else self.app.segments_data
        if not source:
            return

        if not messagebox.askyesno("Confirmar Reseteo", "¿Deseas restaurar todos los segmentos a sus posiciones y audios originales en español?"):
            return

        restored = copy.deepcopy(source)
        if hasattr(self.app.processor, 'processed_segments'):
            self.app.processor.processed_segments.clear()

        for seg in restored:
            if "orig_start_ms" in seg:
                seg["start_ms"] = seg["orig_start_ms"]
            if "orig_end_ms" in seg:
                seg["end_ms"] = seg["orig_end_ms"]

        self.app.processor.metadata = restored
        self.app.segments_data = restored
        self.timeline_ctrl.selected_segment_id = None
        self._update_delete_button_state()
        self.app.pm.save_project_metadata(self.app.current_project, restored)
        self.refresh()
        self.app.notify_metadata_updated()
        messagebox.showinfo("Reseteado", "Todos los segmentos han sido restaurados a sus posiciones originales.")

    def _update_waveforms(self):
        if not self.app.processor or not self.app.processor.original_audio:
            return

        mix = self.app.processor.mix_dubbed_audio()
        duration_ms = len(mix) if mix else len(self.app.processor.original_audio)
        self.total_duration_ms = max(1, duration_ms)
        self.seek_slider.configure(to=self.total_duration_ms)
        self._update_time_label()

        orig_segs_info = []
        source_orig = self.app.master_segments if self.app.master_segments else self.app.processor.metadata
        for s in source_orig:
            s_orig = s.get("orig_start_ms", s.get("start_ms", 0))
            e_orig = s.get("orig_end_ms", s.get("end_ms", 0))
            orig_segs_info.append((s_orig, e_orig, s.get("original", ""), s.get("id", "")))

        dub_segs_info = []
        for s in self.app.processor.metadata:
            dub_segs_info.append((s.get("start_ms", 0), s.get("end_ms", 0), s.get("translated", ""), s.get("id", "")))

        cur_pos = self.seek_slider.get()

        # Calcular zonas de silencio muerto en los clips doblados
        dub_silences = []
        audios_dir = self.app.project_paths.get("audios_dir", "") if self.app.project_paths else ""
        for s in self.app.processor.metadata:
            s_ms = s.get("start_ms", 0)
            e_ms = s.get("end_ms", 0)
            fname = s.get("filename", "")
            voice_dur = 0
            if fname in self.app.processor.processed_segments:
                voice_dur = len(self.app.processor.processed_segments[fname])
            elif fname and audios_dir and os.path.exists(os.path.join(audios_dir, fname)):
                try:
                    fpath = os.path.join(audios_dir, fname)
                    seg_audio = AudioSegment.from_file(fpath)
                    voice_dur = len(seg_audio)
                except Exception:
                    voice_dur = 0

            if voice_dur > 0:
                voice_end = s_ms + voice_dur
                if (e_ms - voice_end) >= 4000: # Solo registrar y resaltar silencios >= 4.0s
                    dur_s = (e_ms - voice_end) / 1000.0
                    dub_silences.append((voice_end, e_ms, s.get("id", ""), dur_s))

        cur_vis_span = self.total_duration_ms / self.zoom_level
        cur_view_range = (self.view_offset_ms, self.view_offset_ms + cur_vis_span)

        # Dibujar Onda Original
        orig_data = self.app.processor.get_waveform_data(self.app.processor.original_audio)
        self.orig_canvas.draw_waveform(
            orig_data, '#38bdf8', self.total_duration_ms,
            segments=orig_segs_info, selected_segment_id=None, playhead_ms=cur_pos,
            view_range=cur_view_range
        )
        self._bind_mousewheel_zoom(self.orig_canvas)
        self.orig_canvas.connect('button_press_event', self._on_orig_click)
        self.orig_canvas.connect('motion_notify_event', self.timeline_ctrl.on_orig_motion)
        self.orig_canvas.connect('figure_leave_event', self.timeline_ctrl.on_orig_leave)

        # Dibujar Onda Doblada
        mix_data = self.app.processor.get_waveform_data(mix)
        self.dub_canvas.draw_waveform(
            mix_data, '#ff7f0e', self.total_duration_ms,
            segments=dub_segs_info, silences=dub_silences,
            selected_segment_id=self.timeline_ctrl.selected_segment_id, playhead_ms=cur_pos,
            view_range=cur_view_range
        )
        self._bind_mousewheel_zoom(self.dub_canvas)
        self.dub_canvas.connect('button_press_event', self.timeline_ctrl.on_timeline_press)
        self.dub_canvas.connect('motion_notify_event', self.timeline_ctrl.on_timeline_motion)
        self.dub_canvas.connect('button_release_event', self.timeline_ctrl.on_timeline_release)
        self.dub_canvas.connect('figure_leave_event', self.timeline_ctrl.on_timeline_leave)

        self.timeline_ctrl.set_silences(dub_silences)

        if self.timeline_ctrl.active_tool == "RAZOR":
            self.dub_canvas.set_cursor("crosshair")

        self._apply_zoom_and_scroll()

    def _on_orig_click(self, event):
        if event.xdata is not None and 0 <= event.xdata <= self.total_duration_ms:
            self._on_seek_from_click(int(event.xdata))

    def _on_seek_from_click(self, ms):
        target_ms = max(0, min(self.total_duration_ms, ms))
        self.seek_slider.set(target_ms)
        self._update_time_label()
        self._update_playhead(target_ms)
        if self.app.playback.is_playing() and self.app.playback.get_playing_id() == "global":
            self._restart_global_playback()

    def _update_playhead(self, current_ms):
        self.orig_canvas.update_playhead(current_ms)
        self.dub_canvas.update_playhead(current_ms)

        # Si el playhead se sale de la pantalla visible mientras se reproduce, desplazar la vista suavemente
        if self.zoom_level > 1.0 and self.app.playback.is_playing() and not self.is_dragging:
            vis_span = self.total_duration_ms / self.zoom_level
            if current_ms > (self.view_offset_ms + vis_span):
                self.view_offset_ms = min(self.total_duration_ms - vis_span, current_ms - (vis_span * 0.15))
                self._apply_zoom_and_scroll()
            elif current_ms < self.view_offset_ms:
                self.view_offset_ms = max(0, current_ms - (vis_span * 0.15))
                self._apply_zoom_and_scroll()

    def _apply_zoom_and_scroll(self):
        if self.total_duration_ms <= 0:
            return
        vis_span = self.total_duration_ms / self.zoom_level
        max_offset = max(0, self.total_duration_ms - vis_span)
        self.view_offset_ms = max(0.0, min(self.view_offset_ms, max_offset))

        x_min = self.view_offset_ms
        x_max = x_min + vis_span

        self.orig_canvas.set_view_range(x_min, x_max)
        self.dub_canvas.set_view_range(x_min, x_max)

        self.lbl_zoom.configure(text=f"🔍 {self.zoom_level:.1f}x")

        if self.zoom_level > 1.0 and max_offset > 0:
            self.h_scrollbar.configure(state="normal")
            pct = (self.view_offset_ms / max_offset) * 100.0
            self.h_scrollbar.set(pct)
        else:
            self.h_scrollbar.configure(state="disabled")
            self.h_scrollbar.set(0)

    def _on_zoom_in(self, target_center_ms=None):
        if self.zoom_level < 8.0:
            if target_center_ms is None:
                cur_pos = self.seek_slider.get()
                vis_span = self.total_duration_ms / self.zoom_level
                if self.view_offset_ms <= cur_pos <= self.view_offset_ms + vis_span:
                    target_center_ms = cur_pos
                else:
                    target_center_ms = self.view_offset_ms + (vis_span / 2)

            self.zoom_level = min(8.0, self.zoom_level * 1.4)
            new_span = self.total_duration_ms / self.zoom_level
            self.view_offset_ms = target_center_ms - (new_span / 2)
            self._apply_zoom_and_scroll()

    def _on_zoom_out(self, target_center_ms=None):
        if self.zoom_level > 1.0:
            if target_center_ms is None:
                target_center_ms = self.view_offset_ms + (self.total_duration_ms / self.zoom_level) / 2

            self.zoom_level = max(1.0, self.zoom_level / 1.4)
            if self.zoom_level == 1.0:
                self.view_offset_ms = 0.0
            else:
                new_span = self.total_duration_ms / self.zoom_level
                self.view_offset_ms = target_center_ms - (new_span / 2)
            self._apply_zoom_and_scroll()

    def _on_zoom_fit(self):
        self.zoom_level = 1.0
        self.view_offset_ms = 0.0
        self._apply_zoom_and_scroll()

    def _on_h_scroll(self, val):
        if self.zoom_level <= 1.0:
            return
        vis_span = self.total_duration_ms / self.zoom_level
        max_offset = max(0, self.total_duration_ms - vis_span)
        self.view_offset_ms = (float(val) / 100.0) * max_offset
        self._apply_zoom_and_scroll()

    def _bind_mousewheel_zoom(self, canvas_comp):
        """Vincula el zoom de rueda directamente al widget Tkinter del canvas para evitar scroll vertical en la ventana."""
        if not canvas_comp or not hasattr(canvas_comp, "canvas") or not canvas_comp.canvas:
            return
        tk_w = canvas_comp.canvas.get_tk_widget()
        if not tk_w:
            return

        def _on_wheel(event):
            w_width = max(1, tk_w.winfo_width())
            vis_span = self.total_duration_ms / max(1.0, self.zoom_level)
            frac = max(0.0, min(1.0, event.x / float(w_width)))
            cursor_ms = self.view_offset_ms + (frac * vis_span)

            if event.delta > 0:
                self._on_zoom_in(target_center_ms=cursor_ms)
            elif event.delta < 0:
                self._on_zoom_out(target_center_ms=cursor_ms)
            return "break"

        def _on_wheel_up(event):
            w_width = max(1, tk_w.winfo_width())
            vis_span = self.total_duration_ms / max(1.0, self.zoom_level)
            frac = max(0.0, min(1.0, event.x / float(w_width)))
            cursor_ms = self.view_offset_ms + (frac * vis_span)
            self._on_zoom_in(target_center_ms=cursor_ms)
            return "break"

        def _on_wheel_down(event):
            w_width = max(1, tk_w.winfo_width())
            vis_span = self.total_duration_ms / max(1.0, self.zoom_level)
            frac = max(0.0, min(1.0, event.x / float(w_width)))
            cursor_ms = self.view_offset_ms + (frac * vis_span)
            self._on_zoom_out(target_center_ms=cursor_ms)
            return "break"

        tk_w.bind("<MouseWheel>", _on_wheel)
        tk_w.bind("<Button-4>", _on_wheel_up)
        tk_w.bind("<Button-5>", _on_wheel_down)

    def _on_canvas_scroll(self, event):
        if event.xdata is None:
            return
        if getattr(event, "button", None) == 'up':
            self._on_zoom_in(target_center_ms=event.xdata)
        elif getattr(event, "button", None) == 'down':
            self._on_zoom_out(target_center_ms=event.xdata)

    def _on_seek_change(self, val):
        self._update_time_label()
        self._update_playhead(float(val))

    def _on_seek_release(self, event):
        self.is_dragging = False
        if self.app.playback.is_playing() and self.app.playback.get_playing_id() == "global":
            self._restart_global_playback()

    def _update_time_label(self):
        cur_ms = int(self.seek_slider.get())
        tot_ms = int(self.total_duration_ms)
        self.lbl_time.configure(text=f"{cur_ms} ms / {tot_ms} ms")

    def _toggle_mute_orig(self):
        self.mute_original = not self.mute_original
        self.btn_mute_orig.configure(fg_color="#dc3545" if self.mute_original else ["#3B8ED0", "#1F6AA5"])

    def _toggle_mute_dub(self):
        self.mute_dubbed = not self.mute_dubbed
        self.btn_mute_dub.configure(fg_color="#dc3545" if self.mute_dubbed else ["#3B8ED0", "#1F6AA5"])

    # ----------------------------------------------------------
    # REPRODUCCIÓN
    # ----------------------------------------------------------
    def _toggle_play_global(self):
        if not self.app.processor or not self.app.processor.original_audio:
            return

        if self.app.playback.is_playing() and self.app.playback.get_playing_id() == "global":
            self.app.playback.stop()
            self.btn_play_mix.configure(text="▶ Reproducir Mezcla", state="normal")
            return

        self.btn_play_mix.configure(text="⏳ Cargando...", state="disabled")

        vol_orig = self.slider_vol_orig.get()
        mute_orig = self.mute_original
        vol_dub = self.slider_vol_dub.get()
        mute_dub = self.mute_dubbed
        start_ms = int(self.seek_slider.get())

        def _prep_and_play():
            try:
                audio_slice = self.app.processor.get_slice_mix(
                    start_ms=start_ms,
                    vol_orig=vol_orig,
                    mute_orig=mute_orig,
                    vol_dub=vol_dub,
                    mute_dub=mute_dub
                )
                if not audio_slice:
                    self.app.run_on_ui_thread(lambda: self.btn_play_mix.configure(text="▶ Reproducir Mezcla", state="normal"))
                    return

                def _start_gui():
                    self.btn_play_mix.configure(text="⏹ Detener", state="normal")

                def _on_tick(elapsed):
                    if not self.is_dragging and elapsed <= self.total_duration_ms:
                        self.app.run_on_ui_thread(lambda: self._sync_playback_ui(elapsed))

                def _on_finished():
                    self.app.run_on_ui_thread(lambda: self._reset_playback_ui())

                self.app.run_on_ui_thread(_start_gui)
                self.app.playback.play_audio(
                    audio_slice,
                    play_id="global",
                    start_offset=start_ms,
                    on_tick=_on_tick,
                    on_finished=_on_finished
                )
            except Exception as e:
                print(f"[ERROR] Error al reproducir mezcla: {e}")
                self.app.run_on_ui_thread(lambda: self.btn_play_mix.configure(text="▶ Reproducir Mezcla", state="normal"))

        threading.Thread(target=_prep_and_play, daemon=True).start()

    def _sync_playback_ui(self, elapsed):
        self.seek_slider.set(elapsed)
        self._update_time_label()
        self._update_playhead(elapsed)

    def _reset_playback_ui(self):
        self.btn_play_mix.configure(text="▶ Reproducir Mezcla")
        if not self.is_dragging:
            self.seek_slider.set(0)
            self._update_time_label()
            self._update_playhead(0)

    def _restart_global_playback(self):
        self.app.playback.stop()
        self._toggle_play_global()

    def _toggle_play_segment_slice(self, segment, btn):
        seg_id = segment.get("id")
        if self.app.playback.is_playing() and self.app.playback.get_playing_id() == seg_id:
            self.app.playback.stop()
            btn.configure(text="▶")
            return

        if not self.app.processor or not self.app.processor.original_audio:
            return

        start = segment.get("start_ms", 0)
        end = segment.get("end_ms", 0)
        orig_slice = self.app.processor.original_audio[start:end]

        fname = segment.get("filename")
        if fname in self.app.processor.processed_segments:
            dub_seg = self.app.processor.processed_segments[fname]
        else:
            dub_seg = AudioSegment.silent(duration=len(orig_slice))

        vol_o = self.slider_vol_orig.get()
        vol_d = self.slider_vol_dub.get()
        db_o = -100 if self.mute_original or vol_o == 0 else 20 * math.log10(vol_o)
        db_d = -100 if self.mute_dubbed or vol_d == 0 else 20 * math.log10(vol_d)

        mixed = (orig_slice + db_o).overlay(dub_seg + db_d)
        btn.configure(text="⏹")

        def _on_finished():
            self.app.run_on_ui_thread(lambda: btn.configure(text="▶"))

        self.app.playback.play_audio(mixed, play_id=seg_id, on_finished=_on_finished)

    # ----------------------------------------------------------
    # EXPORTACIÓN
    # ----------------------------------------------------------
    def _export_audio(self):
        if not self.app.processor:
            return
        default_name = f"{self.app.current_project}_doblado.mp3"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            initialfile=default_name,
            filetypes=[("MP3 Audio", "*.mp3"), ("WAV Audio", "*.wav")],
            title="Guardar Audio Doblado"
        )
        if not save_path:
            return
        try:
            ExportService.export_audio(
                self.app.processor,
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
        video_file = self.app.project_paths.get("video_file") if self.app.project_paths else None
        if not video_file or not os.path.exists(video_file):
            messagebox.showwarning("Atención", "El proyecto actual no tiene un video de origen (.mp4).")
            return
        default_name = f"{self.app.current_project}_video_doblado.mp4"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            initialfile=default_name,
            filetypes=[("Video MP4", "*.mp4")],
            title="Guardar Video Doblado"
        )
        if not save_path:
            return
        try:
            ExportService.export_video(
                self.app.processor,
                video_file,
                save_path,
                vol_orig=self.slider_vol_orig.get(),
                mute_orig=self.mute_original,
                vol_dub=self.slider_vol_dub.get(),
                mute_dub=self.mute_dubbed
            )
            messagebox.showinfo("Exportado", f"Video con audio doblado generado exitosamente en:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error al Exportar Video", str(e))
