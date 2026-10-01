import os
import threading
from tkinter import messagebox
import customtkinter as ctk
import pygame
from ui.widgets.segment_card import SegmentCard

class TabDubbingView(ctk.CTkFrame):
    """Pestaña 2: Doblaje y clonación de voz con Pinokio (0.6B / 1.7B)."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.selected_tts_model = "0.6B"
        self.card_widgets = {}
        self._build_ui()

    def _build_ui(self):
        # Barra superior de acciones
        top_frame = ctk.CTkFrame(self, height=50, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=10)

        self.btn_run_all = ctk.CTkButton(
            top_frame,
            text="🚀 Solicitar Todos a Pinokio",
            font=("Arial", 14, "bold"),
            fg_color="#28a745",
            hover_color="#218838",
            command=self._start_dubbing_all
        )
        self.btn_run_all.pack(side="left", padx=5)

        btn_reload = ctk.CTkButton(top_frame, text="🔄 Recargar", width=100, command=self.refresh)
        btn_reload.pack(side="left", padx=5)

        # Switcher de Modelo TTS (0.6B vs 1.7B)
        model_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        model_frame.pack(side="left", padx=15)
        ctk.CTkLabel(model_frame, text="Modelo TTS:", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 6))

        self.seg_tts_model = ctk.CTkSegmentedButton(
            model_frame,
            values=["0.6B (Rápido)", "1.7B (Calidad)"],
            command=self._on_tts_model_changed
        )
        self.seg_tts_model.set("0.6B (Rápido)")
        self.seg_tts_model.pack(side="left")

        self.lbl_t2_progress = ctk.CTkLabel(top_frame, text="", font=("Arial", 12), text_color="#aaaaaa")
        self.lbl_t2_progress.pack(side="left", padx=15)

        # Contenedor desplazable de tarjetas
        self.scroll_cards = ctk.CTkScrollableFrame(self, label_text="Segmentos a Doblar")
        self.scroll_cards.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def refresh(self):
        for w in self.scroll_cards.winfo_children():
            w.destroy()
        self.card_widgets.clear()

        segments = self.app.segments_data
        if not segments:
            ctk.CTkLabel(
                self.scroll_cards,
                text="No hay segmentos cargados. Completa el Paso 1 primero.",
                text_color="#aaaaaa"
            ).pack(pady=40)
            return

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
                self._start_single_dubbing
            )
            card.pack(fill="x", padx=5, pady=5)
            self.card_widgets[seg['id']] = card

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

    def _on_tts_model_changed(self, value):
        self.selected_tts_model = "0.6B" if "0.6B" in value else "1.7B"

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
            except Exception as e:
                self.app.run_on_ui_thread(
                    lambda: messagebox.showerror("Error en Doblaje", f"Fallo al generar {seg['id']}: {e}")
                )

        threading.Thread(target=_worker, daemon=True).start()

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

        self.btn_run_all.configure(state="disabled", text="Procesando...")

        def _worker():
            total = len(segments)
            for i, seg in enumerate(segments):
                card = self.card_widgets.get(seg['id'])
                if card:
                    self.app.run_on_ui_thread(card.set_processing)
                self.app.run_on_ui_thread(
                    lambda idx=i+1: self.lbl_t2_progress.configure(text=f"Generando {idx} de {total}...")
                )
                try:
                    self._generate_segment_voice(seg)
                    if card:
                        self.app.run_on_ui_thread(card.set_done)
                except Exception as e:
                    print(f"[ERROR] Error generando segmento {seg['id']}: {e}")

            self.app.run_on_ui_thread(self._on_dubbing_all_finished)

        threading.Thread(target=_worker, daemon=True).start()

    def _generate_segment_voice(self, seg):
        tone = seg.get('tone', 'Conversational')
        examples = self.app.pm.get_examples_config()
        tone_map = {ex['tono']: ex['transcripcion'] for ex in examples}

        ref_audio_path = os.path.join(self.app.pm.assets_dir, f"ref_{tone}.wav")
        ref_text = tone_map.get(tone, "This is a reference text.")
        output_path = os.path.join(self.app.project_paths["audios_dir"], seg['filename'])

        # Detener reproducción antes de sobreescribir archivo
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        self.app.pinokio.generate_voice_clone(
            ref_audio_path=ref_audio_path,
            ref_text=ref_text,
            target_text=seg['translated'],
            output_path=output_path,
            model_size=self.selected_tts_model
        )

    def _on_dubbing_all_finished(self):
        self.btn_run_all.configure(state="normal", text="🚀 Solicitar Todos a Pinokio")
        self.lbl_t2_progress.configure(text="¡Todos los segmentos generados!", text_color="#28a745")
        self.app.notify_audio_updated()
        messagebox.showinfo("Completado", "Se han generado todos los audios en la carpeta 'audios' del proyecto.")
