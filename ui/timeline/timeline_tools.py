import os
import copy
from pydub import AudioSegment

class TimelineController:
    """Controlador que gestiona las herramientas (Puntero, Cuchilla, Arrastre, Hover) y la manipulación de clips."""

    def __init__(self, get_processor, get_project_paths, get_master_segments, get_total_duration_ms, 
                 dub_canvas_comp, orig_canvas_comp, callbacks):
        self.get_processor = get_processor
        self.get_project_paths = get_project_paths
        self.get_master_segments = get_master_segments
        self.get_total_duration_ms = get_total_duration_ms
        self.dub_canvas_comp = dub_canvas_comp
        self.orig_canvas_comp = orig_canvas_comp
        self.cb = callbacks

        # Estado de herramienta y selección
        self.active_tool = "SELECT"
        self.selected_segment_id = None

        # Estado de arrastre interactivo (Move / Resize)
        self.drag_mode = None
        self.drag_segment = None
        self.drag_seg_id = None
        self.drag_start_x = 0.0
        self.orig_seg_start = 0
        self.orig_seg_end = 0
        self.orig_clip_raw_duration = 0
        self.drag_has_moved = False

    def set_tool_mode(self, mode):
        """Cambia entre modo 'SELECT' y 'RAZOR'."""
        self.active_tool = mode
        if mode == "SELECT":
            self.dub_canvas_comp.set_cursor("")
            self.dub_canvas_comp.remove_razor_guide()
            self.cb.get("on_hover_dub", lambda t, c: None)(
                "Pasa el cursor sobre la onda doblada para inspeccionar el texto...", "#64748b"
            )
        elif mode == "RAZOR":
            self.dub_canvas_comp.set_cursor("crosshair")
            self.cb.get("on_hover_dub", lambda t, c: None)(
                "✂️ Modo Cuchilla activo: Haz clic sobre la onda doblada para dividir el audio", "#ff5252"
            )

    def find_segment_at_ms(self, ms):
        processor = self.get_processor()
        if not processor or not processor.metadata:
            return None
        for seg in processor.metadata:
            s = seg.get("start_ms", 0)
            e = seg.get("end_ms", 0)
            if s <= ms <= e:
                return seg
        return None

    # ----------------------------------------------------------
    # EVENTOS PISTA DOBLADA (DUB CANVAS)
    # ----------------------------------------------------------
    def on_timeline_motion(self, event):
        processor = self.get_processor()
        if not processor or not processor.metadata:
            return

        tot_duration = self.get_total_duration_ms()

        # CASO 0: Modo Cuchilla
        if self.active_tool == "RAZOR":
            if event.xdata is None or (self.dub_canvas_comp.ax and event.inaxes != self.dub_canvas_comp.ax):
                self.dub_canvas_comp.remove_razor_guide()
                return

            cut_ms = int(event.xdata)
            self.dub_canvas_comp.set_razor_guide(cut_ms)

            target_seg = self.find_segment_at_ms(cut_ms)
            if target_seg:
                self.cb.get("on_hover_dub", lambda t, c: None)(
                    f"✂️ Cuchilla en {cut_ms} ms | Clic para dividir [{target_seg.get('id', '')}]", "#ff5252"
                )
            else:
                self.cb.get("on_hover_dub", lambda t, c: None)(
                    f"✂️ Cuchilla en {cut_ms} ms (fuera de segmento)", "#ffb74d"
                )
            return

        self.dub_canvas_comp.remove_razor_guide()

        # CASO 1: Arrastre Activo (MOVE / RESIZE)
        if self.drag_mode is not None:
            if event.xdata is None:
                return

            self.drag_has_moved = True
            delta_x = event.xdata - self.drag_start_x

            if self.drag_mode == "MOVE":
                dur = self.orig_seg_end - self.orig_seg_start
                new_start = max(0, self.orig_seg_start + delta_x)
                new_end = new_start + dur
                if new_end > tot_duration:
                    new_end = tot_duration
                    new_start = max(0, new_end - dur)

                self.dub_canvas_comp.set_ghost_patch(new_start, new_end, color='#00e5ff', alpha=0.35)
                self.cb.get("on_hover_dub", lambda t, c: None)(
                    f"↔️ Moviendo [{self.drag_seg_id}]: {int(new_start)} ms → {int(new_end)} ms (duración: {int(dur)} ms)", "#00e5ff"
                )
                self.cb.get("on_time_label_update", lambda t: None)(f"{int(new_start)} ms / {int(tot_duration)} ms")

            elif self.drag_mode == "RESIZE":
                new_end = max(self.orig_seg_start + 300, self.orig_seg_end + delta_x)
                if new_end > tot_duration:
                    new_end = tot_duration

                target_dur = max(300, new_end - self.orig_seg_start)
                ratio = self.orig_clip_raw_duration / target_dur if self.orig_clip_raw_duration > 0 else 1.0
                ratio = max(0.5, min(ratio, 5.0))

                self.dub_canvas_comp.set_ghost_patch(self.orig_seg_start, new_end, color='#ffc107', alpha=0.35)
                self.cb.get("on_hover_dub", lambda t, c: None)(
                    f"↔️ Ajustando [{self.drag_seg_id}]: Fin {int(new_end)} ms | Duración: {int(target_dur)} ms (Ratio {ratio:.2f}x)", "#ffc107"
                )
                self.cb.get("on_time_label_update", lambda t: None)(f"{int(new_end)} ms / {int(tot_duration)} ms")

            return

        # CASO 2: Hover normal
        if event.xdata is None:
            self.dub_canvas_comp.set_cursor("")
            self.cb.get("on_hover_dub", lambda t, c: None)(
                "Pasa el cursor sobre la onda doblada para inspeccionar el texto...", "#64748b"
            )
            return

        hovered_text = ""
        tol = max(200.0, tot_duration * 0.015)
        cursor_type = ""

        for seg in processor.metadata:
            s_ms = seg.get("start_ms", 0)
            e_ms = seg.get("end_ms", 0)

            if s_ms <= event.xdata <= e_ms:
                dur = e_ms - s_ms
                hovered_text = f"💬 [{seg.get('id', '')}] ({s_ms} ms - {e_ms} ms | {dur} ms) | \"{seg.get('translated', '')}\""

            if self.dub_canvas_comp.ax and event.inaxes == self.dub_canvas_comp.ax:
                if abs(event.xdata - e_ms) <= tol:
                    cursor_type = "sb_h_double_arrow"
                elif (s_ms + tol) < event.xdata < (e_ms - tol):
                    cursor_type = "fleur"

        self.dub_canvas_comp.set_cursor(cursor_type)
        if hovered_text:
            self.cb.get("on_hover_dub", lambda t, c: None)(hovered_text, "#ffb74d")
        else:
            self.cb.get("on_hover_dub", lambda t, c: None)(
                f"📍 Posición: {int(event.xdata)} ms (silencio / espacio libre)", "#64748b"
            )

    def on_timeline_press(self, event):
        if event.button != 1 or event.xdata is None:
            return
        processor = self.get_processor()
        if not processor:
            return

        click_ms = int(event.xdata)

        # 1. Modo Cuchilla
        if self.active_tool == "RAZOR":
            target_seg = self.find_segment_at_ms(click_ms)
            if target_seg:
                self.split_segment(target_seg, click_ms)
            return

        # 2. Modo Selección
        target_seg = self.find_segment_at_ms(click_ms)
        prev_selected = self.selected_segment_id
        if target_seg:
            self.selected_segment_id = target_seg.get("id")
        else:
            self.selected_segment_id = None

        if prev_selected != self.selected_segment_id:
            self.cb.get("on_selection_changed", lambda s: None)(self.selected_segment_id)

        # Si el clic no fue dentro del eje de la onda, seek directo
        if self.dub_canvas_comp.ax and event.inaxes != self.dub_canvas_comp.ax:
            self.drag_mode = "SEEK"
            self.cb.get("on_seek", lambda ms: None)(click_ms)
            return

        tot_duration = self.get_total_duration_ms()
        tol = max(200.0, tot_duration * 0.015)

        for seg in processor.metadata:
            s_ms = seg.get("start_ms", 0)
            e_ms = seg.get("end_ms", 0)

            # Clic en borde derecho -> RESIZE
            if abs(click_ms - e_ms) <= tol:
                self.drag_mode = "RESIZE"
                self.drag_segment = seg
                self.drag_seg_id = seg.get("id", "")
                self.drag_start_x = click_ms
                self.orig_seg_start = s_ms
                self.orig_seg_end = e_ms
                self.drag_has_moved = False

                fname = seg.get("filename")
                paths = self.get_project_paths()
                fpath = os.path.join(paths["audios_dir"], fname) if paths else ""
                if fname in processor.processed_segments:
                    self.orig_clip_raw_duration = len(processor.processed_segments[fname])
                elif os.path.exists(fpath):
                    self.orig_clip_raw_duration = len(AudioSegment.from_file(fpath))
                else:
                    self.orig_clip_raw_duration = max(300, e_ms - s_ms)
                return

            # Clic en cuerpo -> MOVE
            elif (s_ms + tol) < click_ms < (e_ms - tol):
                self.drag_mode = "MOVE"
                self.drag_segment = seg
                self.drag_seg_id = seg.get("id", "")
                self.drag_start_x = click_ms
                self.orig_seg_start = s_ms
                self.orig_seg_end = e_ms
                self.drag_has_moved = False
                return

        # Clic fuera de segmentos -> SEEK
        self.drag_mode = "SEEK"
        self.cb.get("on_seek", lambda ms: None)(click_ms)

    def on_timeline_release(self, event):
        if self.drag_mode is None:
            return

        mode = self.drag_mode
        seg = self.drag_segment
        has_moved = self.drag_has_moved

        self.drag_mode = None
        self.drag_segment = None
        self.drag_seg_id = None
        self.dub_canvas_comp.remove_ghost_patch()

        tot_duration = self.get_total_duration_ms()

        # Si no hubo movimiento real, tratarlo como clic de seek
        if not has_moved or event.xdata is None or seg is None:
            if mode in ("MOVE", "RESIZE") and event.xdata is not None:
                self.cb.get("on_seek", lambda ms: None)(int(event.xdata))
            return

        delta_x = event.xdata - self.drag_start_x
        processor = self.get_processor()

        if mode == "MOVE":
            dur = self.orig_seg_end - self.orig_seg_start
            new_start = int(max(0, self.orig_seg_start + delta_x))
            new_end = int(new_start + dur)
            if new_end > tot_duration:
                new_end = int(tot_duration)
                new_start = int(max(0, new_end - dur))

            seg["start_ms"] = new_start
            seg["end_ms"] = new_end
            self.cb.get("on_metadata_modified", lambda: None)()

        elif mode == "RESIZE":
            new_end = int(max(self.orig_seg_start + 300, self.orig_seg_end + delta_x))
            if new_end > tot_duration:
                new_end = int(tot_duration)

            seg["end_ms"] = new_end
            target_dur = max(300, new_end - self.orig_seg_start)
            ratio = self.orig_clip_raw_duration / target_dur if self.orig_clip_raw_duration > 0 else 1.0
            ratio = max(0.5, min(ratio, 5.0))

            try:
                processor.process_segment(seg, manual_ratio=ratio)
            except Exception as e:
                print(f"[TimelineController] Error aplicando atempo tras resize: {e}")

            self.cb.get("on_metadata_modified", lambda: None)()

    def on_timeline_leave(self, event):
        if self.drag_mode is None:
            if self.active_tool == "RAZOR":
                self.dub_canvas_comp.set_cursor("crosshair")
            else:
                self.dub_canvas_comp.set_cursor("")
        self.dub_canvas_comp.remove_razor_guide()

        if self.active_tool == "RAZOR":
            self.cb.get("on_hover_dub", lambda t, c: None)(
                "✂️ Modo Cuchilla activo: Haz clic sobre la onda doblada para dividir el audio", "#ff5252"
            )
        else:
            self.cb.get("on_hover_dub", lambda t, c: None)(
                "Pasa el cursor sobre la onda doblada para inspeccionar el texto...", "#64748b"
            )

    # ----------------------------------------------------------
    # EVENTOS PISTA ORIGINAL (ORIG CANVAS)
    # ----------------------------------------------------------
    def on_orig_motion(self, event):
        processor = self.get_processor()
        if not processor or not processor.metadata:
            return
        if event.xdata is None:
            self.cb.get("on_hover_orig", lambda t, c: None)(
                "Pasa el cursor sobre la onda para inspeccionar el texto...", "#64748b"
            )
            return

        x = event.xdata
        hovered_text = ""
        source_orig = self.get_master_segments()
        if not source_orig:
            source_orig = processor.metadata

        for seg in source_orig:
            s_orig = seg.get("orig_start_ms", seg.get("start_ms", 0))
            e_orig = seg.get("orig_end_ms", seg.get("end_ms", 0))
            if s_orig <= x <= e_orig:
                dur = e_orig - s_orig
                hovered_text = f"💬 [{seg.get('id', '')}] ({s_orig} ms - {e_orig} ms | {dur} ms) | \"{seg.get('original', '')}\""
                break

        if hovered_text:
            self.cb.get("on_hover_orig", lambda t, c: None)(hovered_text, "#38bdf8")
        else:
            self.cb.get("on_hover_orig", lambda t, c: None)(
                f"📍 Posición: {int(x)} ms (silencio / fuera de frase)", "#64748b"
            )

    def on_orig_leave(self, event):
        self.cb.get("on_hover_orig", lambda t, c: None)(
            "Pasa el cursor sobre la onda para inspeccionar el texto...", "#64748b"
        )

    # ----------------------------------------------------------
    # OPERACIONES DE CORTE Y SUPRESIÓN
    # ----------------------------------------------------------
    def split_segment(self, segment, cut_ms):
        """Divide el segmento en el punto de corte exacto en milisegundos."""
        processor = self.get_processor()
        paths = self.get_project_paths()
        if not processor or not paths or not segment:
            return

        start_ms = int(segment.get("start_ms", 0))
        end_ms = int(segment.get("end_ms", start_ms))
        cut_ms = int(cut_ms)

        if cut_ms <= start_ms + 2 or cut_ms >= end_ms - 2:
            self.cb.get("on_hover_dub", lambda t, c: None)("⚠️ Haz clic dentro del segmento para cortar", "#ffb74d")
            return

        offset_ms = cut_ms - start_ms
        seg_dur = max(1, end_ms - start_ms)

        fname = segment.get("filename", "")
        fpath = os.path.join(paths["audios_dir"], fname)
        if not os.path.exists(fpath):
            return

        audio = processor.processed_segments.get(fname)
        if not audio:
            try:
                audio = AudioSegment.from_file(fpath)
            except Exception as e:
                print(f"[split_segment] Error cargando audio: {e}")
                return

        audio_len = len(audio)
        if audio_len <= 0:
            audio = AudioSegment.silent(duration=seg_dur)
            audio_len = seg_dur

        if offset_ms >= audio_len:
            part1_audio = audio
            part2_dur = max(10, end_ms - cut_ms)
            part2_audio = AudioSegment.silent(duration=part2_dur)
            is_silence_cut_end = True
            is_silence_cut_start = False
        elif offset_ms <= 0:
            part1_dur = max(10, cut_ms - start_ms)
            part1_audio = AudioSegment.silent(duration=part1_dur)
            part2_audio = audio
            is_silence_cut_end = False
            is_silence_cut_start = True
        else:
            cut_point = max(1, min(audio_len - 1, offset_ms))
            part1_audio = audio[:cut_point]
            part2_audio = audio[cut_point:]
            is_silence_cut_end = False
            is_silence_cut_start = False

        if len(part1_audio) == 0:
            part1_audio = AudioSegment.silent(duration=10)
        if len(part2_audio) == 0:
            part2_audio = AudioSegment.silent(duration=10)

        base, ext = os.path.splitext(fname)
        idx = 1
        part1_name = f"{base}_a{ext}"
        part2_name = f"{base}_b{ext}"
        while os.path.exists(os.path.join(paths["audios_dir"], part1_name)) or \
              os.path.exists(os.path.join(paths["audios_dir"], part2_name)):
            part1_name = f"{base}_p{idx}a{ext}"
            part2_name = f"{base}_p{idx}b{ext}"
            idx += 1

        part1_path = os.path.join(paths["audios_dir"], part1_name)
        part2_path = os.path.join(paths["audios_dir"], part2_name)
        part1_audio.export(part1_path, format="wav")
        part2_audio.export(part2_path, format="wav")

        processor.processed_segments[part1_name] = part1_audio
        processor.processed_segments[part2_name] = part2_audio

        seg_idx = processor.metadata.index(segment)
        seg_a = copy.deepcopy(segment)
        seg_b = copy.deepcopy(segment)

        seg_a["id"] = f"{segment.get('id', 'seg')}_a"
        seg_a["filename"] = part1_name
        seg_a["start_ms"] = start_ms
        seg_a["end_ms"] = cut_ms

        seg_b["id"] = f"{segment.get('id', 'seg')}_b"
        seg_b["filename"] = part2_name
        seg_b["start_ms"] = cut_ms
        seg_b["end_ms"] = end_ms

        if is_silence_cut_end:
            seg_b["translated"] = "[silencio]"
            seg_b["original"] = "[silencio]"
        elif is_silence_cut_start:
            seg_a["translated"] = "[silencio]"
            seg_a["original"] = "[silencio]"

        processor.metadata[seg_idx] = seg_a
        processor.metadata.insert(seg_idx + 1, seg_b)

        self.selected_segment_id = seg_b["id"]
        self.cb.get("on_metadata_modified", lambda: None)()
        self.cb.get("on_hover_dub", lambda t, c: None)(
            f"✂️ Segmento dividido en {cut_ms} ms: [{seg_a['id']}] y [{seg_b['id']}]", "#ff5252"
        )

    def delete_selected_segment(self):
        """Elimina el segmento seleccionado liberando su espacio."""
        if not self.selected_segment_id:
            return
        processor = self.get_processor()
        if not processor:
            return

        target = None
        for s in processor.metadata:
            if s.get("id") == self.selected_segment_id:
                target = s
                break

        if not target:
            return

        processor.metadata.remove(target)
        fname = target.get("filename")
        if fname in processor.processed_segments:
            del processor.processed_segments[fname]

        deleted_id = self.selected_segment_id
        self.selected_segment_id = None

        self.cb.get("on_metadata_modified", lambda: None)()
        self.cb.get("on_hover_dub", lambda t, c: None)(
            f"🗑️ Fragmento [{deleted_id}] eliminado. Espacio liberado.", "#ff5252"
        )
