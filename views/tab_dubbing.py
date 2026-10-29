import os
import threading
from tkinter import messagebox
import customtkinter as ctk
import pygame
from ui.widgets.segment_card import SegmentCard
from ui.dialogs.dubbing_prompt_dialog import DubbingPromptDialog
from core.timing_validator import TimingValidator

class TabDubbingView(ctk.CTkFrame):
    """Pestaña 2: Doblaje y clonación de voz con Pinokio (1.7B)."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.card_widgets = {}
        self.stop_requested = threading.Event()
        self._build_ui()

    def _build_ui(self):
        # Barra superior de acciones
        top_frame = ctk.CTkFrame(self, height=50, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=10)

        self.btn_run_all = ctk.CTkButton(
            top_frame,
            text="🚀 Solicitar Todos (Qwen3-TTS)",
            font=("Arial", 14, "bold"),
            fg_color="#28a745",
            hover_color="#218838",
            command=self._start_dubbing_all
        )
        self.btn_run_all.pack(side="left", padx=5)

        self.btn_stop_dubbing = ctk.CTkButton(
            top_frame,
            text="🛑 Detener",
            font=("Arial", 14, "bold"),
            width=105,
            fg_color="#dc3545",
            hover_color="#c82333",
            state="disabled",
            command=self._stop_dubbing_all
        )
        self.btn_stop_dubbing.pack(side="left", padx=5)

        btn_reload = ctk.CTkButton(top_frame, text="🔄 Recargar", width=100, command=self.refresh)
        btn_reload.pack(side="left", padx=5)


        self.lbl_t2_progress = ctk.CTkLabel(top_frame, text="", font=("Arial", 12), text_color="#aaaaaa")
        self.lbl_t2_progress.pack(side="left", padx=15)

        # Banner de Salud y Consistencia de Tiempos
        self.banner_frame = ctk.CTkFrame(self, height=36, corner_radius=6, border_width=1, fg_color="#1b2e1b", border_color="#2e7d32")
        self.banner_frame.pack(fill="x", padx=10, pady=(0, 8))
        self.lbl_banner = ctk.CTkLabel(self.banner_frame, text="", font=("Arial", 12, "bold"))
        self.lbl_banner.pack(side="left", padx=15, pady=6)

        # Contenedor desplazable de tarjetas
        self.scroll_cards = ctk.CTkScrollableFrame(self, label_text="Segmentos a Doblar")
        self.scroll_cards.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def refresh(self):
        for w in self.scroll_cards.winfo_children():
            w.destroy()
        self.card_widgets.clear()

        segments = self.app.segments_data
        if not segments:
            self.banner_frame.configure(fg_color="#2b2b2b", border_color="#3d3d3d")
            self.lbl_banner.configure(text="ℹ️ No hay segmentos cargados en este proyecto. Ve al Paso 1 para sincronizar.", text_color="#aaaaaa")
            ctk.CTkLabel(
                self.scroll_cards,
                text="No hay segmentos cargados. Completa el Paso 1 primero.",
                text_color="#aaaaaa"
            ).pack(pady=40)
            return

        # Validar salud de tiempos
        val = TimingValidator.validate(segments)
        if not val["has_errors"]:
            self.banner_frame.configure(fg_color="#1b2e1b", border_color="#2e7d32")
            self.lbl_banner.configure(text=val["summary_text"], text_color="#81c784")
        else:
            self.banner_frame.configure(fg_color="#3e1b1b", border_color="#e53935")
            self.lbl_banner.configure(text=val["summary_text"], text_color="#ef9a9a")

        anomalies_map = val["anomalies"]

        audio_file = self.app.project_paths.get("audio_file") if self.app.project_paths else None
        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None

        for seg in segments:
            card = SegmentCard(
                self.scroll_cards,
                seg,
                audio_file,
                audios_dir,
                self._on_segment_saved,
                self._on_segment_deleted,
                self._start_single_dubbing,
                anomalies=anomalies_map.get(seg['id'])
            )
            card.pack(fill="x", padx=5, pady=5)
            self.card_widgets[seg['id']] = card

        self._update_progress_summary()

    def _on_segment_saved(self, updated_seg):
        for i, s in enumerate(self.app.segments_data):
            if s['id'] == updated_seg['id']:
                self.app.segments_data[i] = updated_seg
                break
        self.app.pm.save_project_metadata(self.app.current_project, self.app.segments_data)
        if self.app.processor:
            self.app.processor.metadata = self.app.segments_data
            self.app.processor.recalculate_end_times()

    def _on_segment_deleted(self, seg_to_delete):
        if messagebox.askyesno("Confirmar", f"¿Eliminar el segmento {seg_to_delete['id']}?"):
            self.app.segments_data = [s for s in self.app.segments_data if s['id'] != seg_to_delete['id']]
            self.app.pm.save_project_metadata(self.app.current_project, self.app.segments_data)
            self.refresh()
            self.app.notify_metadata_updated()

    def _update_progress_summary(self):
        segments = self.app.segments_data or []
        if not segments:
            self.lbl_t2_progress.configure(text="", text_color="#aaaaaa")
            return
        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None
        gen_count = 0
        if audios_dir and os.path.exists(audios_dir):
            for s in segments:
                fn = s.get('filename', '')
                fp = os.path.join(audios_dir, fn)
                if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                    gen_count += 1
        total = len(segments)
        pct = (gen_count / total * 100.0) if total > 0 else 0
        if gen_count == total:
            self.lbl_t2_progress.configure(text=f"📊 {gen_count} de {total} generados (100% completado)", text_color="#81c784")
        elif gen_count > 0:
            self.lbl_t2_progress.configure(text=f"📊 {gen_count} de {total} generados ({pct:.0f}%)", text_color="#ffb74d")
        else:
            self.lbl_t2_progress.configure(text=f"📊 0 de {total} generados (0%)", text_color="#aaaaaa")

    def _start_single_dubbing(self, seg):
        if not self.app.pinokio.check_connection():
            messagebox.showerror(
                "Pinokio Desconectado",
                "No se puede conectar a Pinokio en http://127.0.0.1:7860.\nAsegúrate de tener iniciada la app de TTS en Pinokio."
            )
            return

        card = self.card_widgets.get(seg['id'])
        if card:
            card.set_processing()

        def _worker():
            try:
                self._generate_segment_voice(seg)
                self.app.run_on_ui_thread(lambda: card.set_done() if card else None)
                self.app.run_on_ui_thread(lambda: self.app.notify_audio_updated())
                self.app.run_on_ui_thread(self._update_progress_summary)
            except Exception as e:
                self.app.run_on_ui_thread(
                    lambda: messagebox.showerror("Error en Doblaje", f"Fallo al generar {seg['id']}: {e}")
                )
                if card:
                    self.app.run_on_ui_thread(card.update_status)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_dubbing_all(self):
        self.stop_requested.set()
        self.btn_stop_dubbing.configure(state="disabled", text="Deteniendo...")
        self.lbl_t2_progress.configure(text="Deteniendo tras el segmento actual...", text_color="#ffc107")

    def _start_dubbing_all(self):
        if not self.app.pinokio.check_connection():
            messagebox.showerror(
                "Pinokio Desconectado",
                "No se puede conectar a Pinokio en http://127.0.0.1:7860.\nAsegúrate de tener iniciada la app de TTS en Pinokio."
            )
            return

        segments = self.app.segments_data
        if not segments:
            messagebox.showwarning("Atención", "No hay segmentos para doblar.")
            return

        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None

        # Clasificar existentes vs faltantes
        existing_segs = []
        missing_segs = []
        for seg in segments:
            fname = seg.get('filename', '')
            fpath = os.path.join(audios_dir, fname) if audios_dir and fname else None
            if fpath and os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
                existing_segs.append(seg)
            else:
                missing_segs.append(seg)

        mode = "all"
        if len(existing_segs) == 0:
            target_segments = segments
            mode = "all"
        elif len(missing_segs) == 0:
            # Todos los segmentos ya están generados
            resp = messagebox.askyesno(
                "Segmentos Ya Generados",
                f"Todos los {len(segments)} segmentos ya tienen audio generado.\n\n"
                "¿Deseas reemplazarlos todos y regenerarlos desde cero?"
            )
            if not resp:
                return
            target_segments = segments
            mode = "all"
        else:
            # Diálogo modal: faltantes vs reemplazar
            dialog = DubbingPromptDialog(
                self.winfo_toplevel(),
                existing_count=len(existing_segs),
                missing_count=len(missing_segs),
                total_count=len(segments)
            )
            choice = dialog.show()
            if choice == "missing":
                target_segments = missing_segs
                mode = "missing"
            elif choice == "all":
                target_segments = segments
                mode = "all"
            else:
                return

        self.stop_requested.clear()
        self.btn_run_all.configure(state="disabled", text="Procesando...")
        self.btn_stop_dubbing.configure(state="normal", text="🛑 Detener")

        def _worker():
            total = len(target_segments)
            was_stopped = False
            generated_count = 0

            # Asegurar descarga obligatoria de Whisper de VRAM antes de iniciar Qwen3-TTS
            if hasattr(self.app, "aligner") and self.app.aligner:
                self.app.aligner.unload_model()

            for i, seg in enumerate(target_segments):
                if self.stop_requested.is_set():
                    was_stopped = True
                    break

                card = self.card_widgets.get(seg['id'])
                if card:
                    self.app.run_on_ui_thread(card.set_processing)
                
                label_prefix = "Generando faltante" if mode == "missing" else "Generando"
                self.app.run_on_ui_thread(
                    lambda idx=i+1, sid=seg.get('id', ''): self.lbl_t2_progress.configure(
                        text=f"{label_prefix} {idx} de {total} (ID: {sid})...",
                        text_color="#38bdf8"
                    )
                )
                try:
                    self._generate_segment_voice(seg)
                    generated_count += 1
                    if card:
                        self.app.run_on_ui_thread(card.set_done)
                except Exception as e:
                    print(f"[ERROR] Error generando segmento {seg['id']}: {e}")
                    if card:
                        self.app.run_on_ui_thread(card.update_status)

            self.app.run_on_ui_thread(lambda: self._on_dubbing_all_finished(was_stopped, generated_count, total, mode))

        threading.Thread(target=_worker, daemon=True).start()

    def _generate_segment_voice(self, seg):
        lang = self.app.pm.get_project_language(self.app.current_project)
        tone = seg.get('tone', 'Conversational')
        examples_dir = self.app.pm.get_clone_examples_dir(lang)
        examples = self.app.pm.get_examples_config(lang)
        tone_map = {ex['tono']: ex['transcripcion'] for ex in examples}

        ref_audio_path = os.path.join(examples_dir, f"ref_{tone}.wav")
        ref_text = tone_map.get(tone, "This is a reference text.")
        output_path = os.path.join(self.app.project_paths["audios_dir"], seg['filename'])

        # Detener reproducción antes de sobreescribir archivo
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        pinokio_lang = "Portuguese" if lang == "pt" else "English"
        # Asegurar descarga preventiva de Whisper de VRAM
        if hasattr(self.app, "aligner") and self.app.aligner:
            self.app.aligner.unload_model()

        self.app.pinokio.generate_voice_clone(
            ref_audio_path=ref_audio_path,
            ref_text=ref_text,
            target_text=seg['translated'],
            output_path=output_path,
            language=pinokio_lang,
            model_size="1.7B"
        )

    def _on_dubbing_all_finished(self, was_stopped=False, count=0, total=0, mode="all"):
        self.btn_run_all.configure(state="normal", text="🚀 Solicitar Todos (Qwen3-TTS)")
        self.btn_stop_dubbing.configure(state="disabled", text="🛑 Detener")
        self.app.notify_audio_updated()
        self._update_progress_summary()

        segments = self.app.segments_data or []
        audios_dir = self.app.project_paths.get("audios_dir") if self.app.project_paths else None
        total_project = len(segments)
        actual_gen = 0
        if audios_dir and os.path.exists(audios_dir):
            for s in segments:
                fn = s.get('filename', '')
                fp = os.path.join(audios_dir, fn)
                if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                    actual_gen += 1

        if was_stopped:
            self.lbl_t2_progress.configure(
                text=f"Generación detenida ({count}/{total} de la tanda). Total: {actual_gen}/{total_project}.",
                text_color="#ffb74d"
            )
            messagebox.showinfo(
                "Proceso Detenido",
                f"Se detuvo la solicitud a Pinokio.\nSe completaron {count} de {total} segmentos de esta tanda."
            )
        else:
            if mode == "missing":
                self.lbl_t2_progress.configure(
                    text=f"¡Faltantes completados! ({actual_gen}/{total_project} generados)",
                    text_color="#28a745"
                )
                messagebox.showinfo(
                    "Completado",
                    f"Se completó con éxito la generación de los {count} segmentos faltantes."
                )
            else:
                self.lbl_t2_progress.configure(
                    text=f"¡Todos los segmentos generados! ({actual_gen}/{total_project})",
                    text_color="#28a745"
                )
                messagebox.showinfo(
                    "Completado",
                    "Se han generado todos los audios en la carpeta 'audios' del proyecto."
                )
