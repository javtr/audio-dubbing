import os
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

        self._build_ui()
        self._init_timeline_controller()
        self._bind_shortcuts()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=2)
        self.grid_columnconfigure(0, weight=1)

        # --- ZONA SUPERIOR: FORMAS DE ONDA ---
        wave_frame = ctk.CTkFrame(self)
        wave_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        wave_frame.grid_columnconfigure(0, weight=1)
        wave_frame.grid_rowconfigure(0, weight=1)
        wave_frame.grid_rowconfigure(1, weight=1)

        # 1. Pista Original
        orig_box = ctk.CTkFrame(wave_frame)
        orig_box.grid(row=0, column=0, sticky="nsew", padx=5, pady=3)
        orig_box.grid_columnconfigure(0, weight=1)
        orig_box.grid_rowconfigure(1, weight=1)
        orig_box.grid_rowconfigure(2, weight=0)

        orig_header = ctk.CTkFrame(orig_box, fg_color="transparent")
        orig_header.grid(row=0, column=0, sticky="ew", padx=8, pady=2)
        ctk.CTkLabel(orig_header, text="Pista Original", font=("Arial", 12, "bold")).pack(side="left")
        self.btn_mute_orig = ctk.CTkButton(orig_header, text="Mute", width=55, height=24, command=self._toggle_mute_orig)
        self.btn_mute_orig.pack(side="left", padx=10)
        self.slider_vol_orig = ctk.CTkSlider(orig_header, from_=0, to=2, width=120)
        self.slider_vol_orig.set(1.0)
        self.slider_vol_orig.pack(side="left", padx=5)

        self.orig_canvas_frame = ctk.CTkFrame(orig_box)
        self.orig_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        self.orig_canvas = TimelineCanvas(self.orig_canvas_frame, is_dubbed=False)

        orig_footer = ctk.CTkFrame(orig_box, height=26, fg_color="#181818", corner_radius=4)
        orig_footer.grid(row=2, column=0, sticky="ew", padx=5, pady=(1, 3))
        self.lbl_orig_hover = ctk.CTkLabel(
            orig_footer,
            text="Pasa el cursor sobre la onda para inspeccionar el texto...",
            font=("Arial", 11),
            text_color="#64748b",
            anchor="w"
        )
        self.lbl_orig_hover.pack(side="left", padx=10, fill="x", expand=True)

        # 2. Pista Doblada
        dub_box = ctk.CTkFrame(wave_frame)
        dub_box.grid(row=1, column=0, sticky="nsew", padx=5, pady=3)
        dub_box.grid_columnconfigure(0, weight=1)
        dub_box.grid_rowconfigure(1, weight=1)
        dub_box.grid_rowconfigure(2, weight=0)

        dub_header = ctk.CTkFrame(dub_box, fg_color="transparent")
        dub_header.grid(row=0, column=0, sticky="ew", padx=8, pady=2)
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

        self.btn_reset_dub = ctk.CTkButton(
            dub_header, text="↺ Resetear a Original", width=145, height=24,
            fg_color="#a83232", hover_color="#822727",
            command=self._reset_dubbed_positions
        )
        self.btn_reset_dub.pack(side="right", padx=10)

        self.dub_canvas_frame = ctk.CTkFrame(dub_box)
        self.dub_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        self.dub_canvas = TimelineCanvas(self.dub_canvas_frame, is_dubbed=True)

        dub_footer = ctk.CTkFrame(dub_box, height=26, fg_color="#181818", corner_radius=4)
        dub_footer.grid(row=2, column=0, sticky="ew", padx=5, pady=(1, 3))
        self.lbl_dub_hover = ctk.CTkLabel(
            dub_footer,
            text="Pasa el cursor sobre la onda doblada para inspeccionar el texto...",
            font=("Arial", 11),
            text_color="#64748b",
            anchor="w"
        )
        self.lbl_dub_hover.pack(side="left", padx=10, fill="x", expand=True)

        # --- ZONA MEDIA: SEGMENTOS GRANULARES ---
        self.mid_scroll = ctk.CTkScrollableFrame(self, label_text="Ajuste Fino de Segmentos")
        self.mid_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # --- BARRA DE PROGRESO / SEEK ---
        seek_frame = ctk.CTkFrame(self)
        seek_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.seek_slider = ctk.CTkSlider(seek_frame, from_=0, to=100, command=self._on_seek_change)
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self.seek_slider.bind("<ButtonPress-1>", lambda e: setattr(self, 'is_dragging', True))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)

        self.lbl_time = ctk.CTkLabel(seek_frame, text="0 ms / 0 ms", width=150, font=("Consolas", 12, "bold"))
        self.lbl_time.pack(side="right", padx=10)

        # --- ZONA INFERIOR: BOTONES GLOBALES Y EXPORTACIÓN ---
        bot_frame = ctk.CTkFrame(self)
        bot_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=8)

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
        self._update_waveforms()

    def _on_metadata_modified(self):
        self.app.processor.recalculate_end_times()
        self.app.pm.save_project_metadata(self.app.current_project, self.app.processor.metadata)
        self.refresh()
        self.app.notify_metadata_updated()

    def _delete_selected_segment(self):
        self.timeline_ctrl.delete_selected_segment()

    def _update_delete_button_state(self):
        if self.timeline_ctrl.selected_segment_id:
            self.btn_delete_seg.configure(state="normal", fg_color="#c62828")
        else:
            self.btn_delete_seg.configure(state="disabled", fg_color="#2b2b2b")

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

        # Dibujar Onda Original
        orig_data = self.app.processor.get_waveform_data(self.app.processor.original_audio)
        self.orig_canvas.draw_waveform(
            orig_data, '#38bdf8', self.total_duration_ms,
            segments=orig_segs_info, selected_segment_id=None, playhead_ms=cur_pos
        )
        self.orig_canvas.connect('button_press_event', self._on_orig_click)
        self.orig_canvas.connect('motion_notify_event', self.timeline_ctrl.on_orig_motion)
        self.orig_canvas.connect('figure_leave_event', self.timeline_ctrl.on_orig_leave)

        # Dibujar Onda Doblada
        mix_data = self.app.processor.get_waveform_data(mix)
        self.dub_canvas.draw_waveform(
            mix_data, '#ff7f0e', self.total_duration_ms,
            segments=dub_segs_info, selected_segment_id=self.timeline_ctrl.selected_segment_id, playhead_ms=cur_pos
        )
        self.dub_canvas.connect('button_press_event', self.timeline_ctrl.on_timeline_press)
        self.dub_canvas.connect('motion_notify_event', self.timeline_ctrl.on_timeline_motion)
        self.dub_canvas.connect('button_release_event', self.timeline_ctrl.on_timeline_release)
        self.dub_canvas.connect('figure_leave_event', self.timeline_ctrl.on_timeline_leave)

        if self.timeline_ctrl.active_tool == "RAZOR":
            self.dub_canvas.set_cursor("crosshair")

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
        if not self.app.processor:
            return

        if self.app.playback.is_playing() and self.app.playback.get_playing_id() == "global":
            self.app.playback.stop()
            self.btn_play_mix.configure(text="▶ Reproducir Mezcla")
            return

        mix = self.app.processor.get_current_mix(
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

        def _on_tick(elapsed):
            if not self.is_dragging and elapsed <= self.total_duration_ms:
                self.app.run_on_ui_thread(lambda: self._sync_playback_ui(elapsed))

        def _on_finished():
            self.app.run_on_ui_thread(lambda: self._reset_playback_ui())

        self.app.playback.play_audio(
            audio_slice,
            play_id="global",
            start_offset=start_ms,
            on_tick=_on_tick,
            on_finished=_on_finished
        )

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
        default_name = f"{self.app.current_project}_doblado.wav"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            initialfile=default_name,
            filetypes=[("WAV Audio", "*.wav"), ("MP3 Audio", "*.mp3")],
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
