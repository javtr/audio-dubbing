import os
import json
import math
import subprocess
import time
import tempfile
import shutil
import numpy as np
from pydub import AudioSegment
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

def check_ffmpeg():
    """Verifica si FFmpeg está instalado en el sistema."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

class AudioProcessor:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.metadata_path = os.path.join(root_dir, "files", "original", "secciones.json")
        self.audio_dir = os.path.join(root_dir, "files", "audios")
        self.original_audio_path = self._find_original_audio()
        
        self.original_audio = None
        self.segments_data = []
        self.processed_segments = {} 
        
        self.dubbed_audio = None
        self.temp_dir = tempfile.mkdtemp()
        
    def _find_original_audio(self):
        folder = os.path.join(self.root_dir, "files", "original")
        if not os.path.exists(folder):
            return None
        for f in os.listdir(folder):
            if f.startswith("original") and f.endswith((".mp3", ".wav")):
                return os.path.join(folder, f)
        return None
        
    def load_data(self):
        if not self.original_audio_path or not os.path.exists(self.metadata_path):
            print(self.original_audio_path)
            print(self.metadata_path)
            raise FileNotFoundError("No se encontró el audio original o 'secciones.json' en files/original.")
            
        self.original_audio = AudioSegment.from_file(self.original_audio_path)
        with open(self.metadata_path, 'r', encoding='utf-8') as f:
            self.segments_data = json.load(f)
        self.recalculate_end_times()

    def recalculate_end_times(self):
        """Calcula end_ms basado en el start_ms del siguiente segmento."""
        if not self.segments_data or self.original_audio is None:
            return
        
        # Sanitizar start_ms para evitar TypeError al ordenar si existen valores null
        for seg in self.segments_data:
            if seg.get('start_ms') is None:
                seg['start_ms'] = 0

        # Asegurar orden cronológico para el cálculo
        self.segments_data.sort(key=lambda x: x['start_ms'])
        
        for i in range(len(self.segments_data) - 1):
            self.segments_data[i]['end_ms'] = self.segments_data[i+1]['start_ms']
            
        self.segments_data[-1]['end_ms'] = len(self.original_audio)
            
    def process_segment(self, segment, manual_ratio=None):
        filename = segment["filename"]
        filepath = os.path.join(self.audio_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Archivo de audio no encontrado: {filepath}")
            
        audio = AudioSegment.from_file(filepath)
        actual_duration = len(audio)
        target_duration = segment["end_ms"] - segment["start_ms"]
        
        ratio = 1.0
        if manual_ratio is not None:
            ratio = manual_ratio
        elif actual_duration > target_duration and target_duration > 0:
            ratio = actual_duration / target_duration
            
        if ratio != 1.0:
            out_path = os.path.join(self.temp_dir, f"stretched_{filename}")
            self._apply_atempo(filepath, out_path, ratio)
            processed_audio = AudioSegment.from_file(out_path)
        else:
            processed_audio = audio
            
        self.processed_segments[filename] = processed_audio
        return processed_audio, ratio

    def _apply_atempo(self, input_path, output_path, ratio):
        # Restringimos el ratio a los límites de atempo (0.5 a 100.0) soportados por versiones recientes
        ratio = max(0.5, min(ratio, 100.0))
        cmd = [
            "ffmpeg", "-y", "-i", input_path, 
            "-filter:a", f"atempo={ratio}", 
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
    def mix_dubbed_audio(self):
        mix = AudioSegment.silent(duration=len(self.original_audio))
        for seg in self.segments_data:
            filename = seg["filename"]
            if filename in self.processed_segments:
                seg_audio = self.processed_segments[filename]
                mix = mix.overlay(seg_audio, position=seg["start_ms"])
        self.dubbed_audio = mix
        return mix
        
    def get_waveform_data(self, audio_segment, max_points=1000):
        samples = np.array(audio_segment.get_array_of_samples())
        if audio_segment.channels == 2:
            samples = samples[::2]
        if len(samples) > max_points:
            factor = len(samples) // max_points
            samples = samples[::factor]
        return samples
        
    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class AppUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Audio Dubbing Studio")
        self.geometry("1024x768")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.processor = None
        self.segment_widgets = {}
        
        # Variables de estado de audio
        self.mute_original = False
        self.mute_dubbed = False
        self.playing_id = None
        
        self.is_dragging = False
        self.total_duration = 100
        self.play_start_sys_time = 0
        self.play_start_offset = 0
        
        self.setup_ui()
        
    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1) 
        self.grid_rowconfigure(1, weight=2) 
        self.grid_rowconfigure(2, weight=0) 
        self.grid_rowconfigure(3, weight=0) 
        self.grid_columnconfigure(0, weight=1)
        
        # --- ZONA SUPERIOR (Pistas Globales) ---
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.top_frame.grid_columnconfigure(0, weight=1)
        self.top_frame.grid_rowconfigure(0, weight=1)
        self.top_frame.grid_rowconfigure(1, weight=1)
        
        # Pista Original
        self.orig_track_frame = ctk.CTkFrame(self.top_frame)
        self.orig_track_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.orig_track_frame.grid_rowconfigure(1, weight=1)
        self.orig_track_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.orig_track_frame, text="Pista Original", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.orig_canvas_frame = ctk.CTkFrame(self.orig_track_frame)
        self.orig_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        orig_ctrl_frame = ctk.CTkFrame(self.orig_track_frame)
        orig_ctrl_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.btn_mute_orig = ctk.CTkButton(orig_ctrl_frame, text="Mute", width=60, command=self.toggle_mute_orig)
        self.btn_mute_orig.pack(side="left", padx=5)
        self.slider_vol_orig = ctk.CTkSlider(orig_ctrl_frame, from_=0, to=2)
        self.slider_vol_orig.set(1.0)
        self.slider_vol_orig.pack(side="left", fill="x", expand=True, padx=10)
        
        # Pista Doblada
        self.dub_track_frame = ctk.CTkFrame(self.top_frame)
        self.dub_track_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.dub_track_frame.grid_rowconfigure(1, weight=1)
        self.dub_track_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.dub_track_frame, text="Pista Doblada", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.dub_canvas_frame = ctk.CTkFrame(self.dub_track_frame)
        self.dub_canvas_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        dub_ctrl_frame = ctk.CTkFrame(self.dub_track_frame)
        dub_ctrl_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.btn_mute_dub = ctk.CTkButton(dub_ctrl_frame, text="Mute", width=60, command=self.toggle_mute_dub)
        self.btn_mute_dub.pack(side="left", padx=5)
        self.slider_vol_dub = ctk.CTkSlider(dub_ctrl_frame, from_=0, to=2)
        self.slider_vol_dub.set(1.0)
        self.slider_vol_dub.pack(side="left", fill="x", expand=True, padx=10)
        
        # --- ZONA MEDIA (Control Granular) ---
        self.mid_frame = ctk.CTkScrollableFrame(self, label_text="Segmentos de Audio")
        self.mid_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # --- ZONA BARRA DE PROGRESO ---
        self.seek_frame = ctk.CTkFrame(self)
        self.seek_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(10, 0))
        
        self.seek_slider = ctk.CTkSlider(self.seek_frame, from_=0, to=100, command=self.on_slider_change)
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        
        self.seek_slider.bind("<ButtonPress-1>", self.on_seek_press)
        self.seek_slider.bind("<ButtonRelease-1>", self.on_seek_release)
        
        self.time_label = ctk.CTkLabel(self.seek_frame, text="00:00 / 00:00", width=80)
        self.time_label.pack(side="right", padx=10)
        
        # --- ZONA INFERIOR (Exportación) ---
        self.bot_frame = ctk.CTkFrame(self)
        self.bot_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        
        self.btn_load = ctk.CTkButton(self.bot_frame, text="Cargar Proyecto", command=self.load_project)
        self.btn_load.pack(side="left", padx=20, pady=15)
        
        self.btn_apply_times = ctk.CTkButton(self.bot_frame, text="Aplicar Tiempos", 
                                             command=self.apply_timing_changes,
                                             fg_color="#ffc107", text_color="black", hover_color="#d39e00")
        self.btn_apply_times.pack(side="left", padx=5, pady=15)
        
        self.btn_play_global = ctk.CTkButton(self.bot_frame, text="▶ Reproducir Mezcla", 
                                        font=("Arial", 16, "bold"), fg_color="#007bff", hover_color="#0056b3",
                                        command=self.toggle_play_global)
        self.btn_play_global.pack(side="left", padx=5, pady=15)
        
        self.btn_export = ctk.CTkButton(self.bot_frame, text="Exportar Audio Doblado", 
                                        font=("Arial", 16, "bold"), fg_color="#28a745", hover_color="#218838", 
                                        command=self.export_audio)
        self.btn_export.pack(side="right", padx=20, pady=15)

    def toggle_mute_orig(self):
        self.mute_original = not self.mute_original
        color = "#dc3545" if self.mute_original else ["#3B8ED0", "#1F6AA5"]
        self.btn_mute_orig.configure(fg_color=color)
        
    def toggle_mute_dub(self):
        self.mute_dubbed = not self.mute_dubbed
        color = "#dc3545" if self.mute_dubbed else ["#3B8ED0", "#1F6AA5"]
        self.btn_mute_dub.configure(fg_color=color)

    def draw_waveform(self, frame, samples, color, segments=None):
        for widget in frame.winfo_children():
            widget.destroy()
            
        fig, ax = plt.subplots(figsize=(4, 1), dpi=80)
        fig.patch.set_facecolor('#2b2b2b')
        ax.set_facecolor('#2b2b2b')
        ax.plot(samples, color=color, linewidth=0.5)
        
        if segments:
            total_samples = len(samples)
            for start_frac, end_frac in segments:
                start_idx = int(start_frac * total_samples)
                end_idx = int(end_frac * total_samples)
                ax.axvspan(start_idx, end_idx, color='white', alpha=0.15)
                ax.axvline(x=start_idx, color='#dc3545', linestyle='--', linewidth=1)
                ax.axvline(x=end_idx, color='#dc3545', linestyle='--', linewidth=1)
                
        ax.axis('off')
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)
        
    def format_time(self, ms):
        seconds = int(ms / 1000)
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:02d}:{secs:02d}"

    def update_time_label(self):
        value = self.seek_slider.get()
        cur_str = self.format_time(value)
        tot_str = self.format_time(self.total_duration)
        self.time_label.configure(text=f"{cur_str} / {tot_str}")

    def on_slider_change(self, value):
        self.update_time_label()

    def on_seek_press(self, event):
        self.is_dragging = True

    def on_seek_release(self, event):
        self.is_dragging = False
        if self.playing_id == "global":
            self.restart_global_playback()
            
    def restart_global_playback(self):
        if self.playing_id == "global":
            self.stop_audio()
            mix = self.get_current_mix()
            if mix:
                start_ms = int(self.seek_slider.get())
                if start_ms >= len(mix):
                    start_ms = 0
                    self.seek_slider.set(0)
                audio_to_play = mix[start_ms:]
                self.btn_play_global.configure(text="⏹")
                self.play_audio(audio_to_play, self.btn_play_global, "▶ Reproducir Mezcla", "global", start_offset=start_ms)

    def load_project(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta raíz del proyecto")
        if not folder: return
        
        try:
            self.processor = AudioProcessor(folder)
            self.processor.load_data()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
            
        # Limpiar lista anterior
        for widget in self.mid_frame.winfo_children():
            widget.destroy()
        self.segment_widgets.clear()
        
        self.process_all_segments()

    def process_all_segments(self):
        for seg in self.processor.segments_data:
            try:
                _, ratio = self.processor.process_segment(seg)
                self.add_segment_row(seg, ratio)
            except Exception as e:
                print(f"Error procesando {seg['filename']}: {e}")
                
        self.update_waveforms()

    def add_segment_row(self, segment, ratio):
        row_frame = ctk.CTkFrame(self.mid_frame)
        row_frame.pack(fill="x", pady=4, padx=5)
        
        # Configurar columnas para mantener la alineación tabular entre filas
        row_frame.grid_columnconfigure(2, weight=1) 

        btn_play = ctk.CTkButton(row_frame, text="▶", width=30)
        btn_play.configure(command=lambda s=segment, b=btn_play: self.toggle_play_segment(s, b))
        btn_play.grid(row=0, column=0, padx=5, pady=5)
        
        lbl_file = ctk.CTkLabel(row_frame, text=segment["filename"], width=100, anchor="w")
        lbl_file.grid(row=0, column=1, padx=(5,0), pady=5)
        
        # Espacio fijo para el texto con wraplength para evitar el desplazamiento horizontal de otros elementos
        lbl_text = ctk.CTkLabel(row_frame, text=segment.get("translated", ""), wraplength=350, justify="left", anchor="w")
        lbl_text.grid(row=0, column=2, padx=10, pady=5, sticky="ew")

        # Contenedor para agrupar controles de tiempo y ratio de forma alineada a la derecha
        ctrl_group = ctk.CTkFrame(row_frame, fg_color="transparent")
        ctrl_group.grid(row=0, column=3, padx=5, pady=5, sticky="e")

        ctk.CTkLabel(ctrl_group, text="Inicio (ms):").pack(side="left", padx=(10, 2))
        entry_start = ctk.CTkEntry(ctrl_group, width=70)
        entry_start.insert(0, str(segment["start_ms"]))
        entry_start.pack(side="left", padx=2)

        ctk.CTkLabel(ctrl_group, text=f"Fin: {segment['end_ms']}ms", text_color="#aaaaaa").pack(side="left", padx=(10, 5))
        
        ctk.CTkLabel(ctrl_group, text="Ratio:").pack(side="left", padx=(10, 2))
        entry_ratio = ctk.CTkEntry(ctrl_group, width=60)
        entry_ratio.insert(0, f"{ratio:.2f}")
        entry_ratio.pack(side="left", padx=2)
        
        btn_gen = ctk.CTkButton(ctrl_group, text="Generar", width=80, 
                                command=lambda s=segment, e=entry_ratio: self.regenerate_segment(s, e))
        btn_gen.pack(side="left", padx=5)
        
        self.segment_widgets[segment["id"]] = {
            "frame": row_frame, 
            "entry_ratio": entry_ratio, 
            "btn_play": btn_play,
            "entry_start": entry_start
        }

    def regenerate_segment(self, segment, entry_widget):
        try:
            new_ratio = float(entry_widget.get()) # type: ignore
        except ValueError:
            messagebox.showerror("Error", "El ratio debe ser un número válido.")
            return
            
        try:
            self.processor.process_segment(segment, manual_ratio=new_ratio)
            self.update_waveforms()
            messagebox.showinfo("Éxito", f"Segmento {segment['filename']} regenerado satisfactoriamente.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def apply_timing_changes(self):
        if not self.processor:
            messagebox.showwarning("Atención", "No hay un proyecto cargado.")
            return

        try:
            # 1. Validar todos los inputs antes de aplicar cambios
            new_starts = {}
            for seg_id, widgets in self.segment_widgets.items():
                try:
                    start_ms = int(widgets["entry_start"].get())
                except ValueError:
                    raise ValueError(f"Valor no numérico en uno de los campos de inicio.")

                if start_ms < 0:
                    raise ValueError(f"El tiempo de inicio debe ser positivo.")
                
                new_starts[seg_id] = start_ms

            # 2. Si todo es válido, aplicar al modelo de datos
            for seg in self.processor.segments_data:
                if seg["id"] in new_starts:
                    seg["start_ms"] = new_starts[seg["id"]]
            
            # 3. Recalcular finales automáticamente
            self.processor.recalculate_end_times()
                    
            # Guardar los cambios permanentemente en el archivo JSON
            try:
                # Crear una copia para guardar sin la clave 'end_ms'
                data_to_save = []
                for seg in self.processor.segments_data:
                    clean_seg = {k: v for k, v in seg.items() if k != 'end_ms'}
                    data_to_save.append(clean_seg)

                with open(self.processor.metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            except Exception as e:
                messagebox.showerror("Error de Escritura", f"No se pudo guardar el JSON original:\n{str(e)}")
            
            # 3. Limpiar UI y recargar todo
            for widget in self.mid_frame.winfo_children():
                widget.destroy()
            self.segment_widgets.clear()
            self.process_all_segments()
            messagebox.showinfo("Éxito", "Tiempos actualizados y proyecto recargado.")
        except ValueError as e:
            messagebox.showerror("Error de Formato", str(e))

    def update_waveforms(self):
        if not self.processor: return
        
        orig_data = self.processor.get_waveform_data(self.processor.original_audio)
        self.draw_waveform(self.orig_canvas_frame, orig_data, '#1f77b4') # Azul
        
        mix = self.processor.mix_dubbed_audio()
        mix_data = self.processor.get_waveform_data(mix)
        
        segments_info = []
        duration_ms = len(mix)
        if duration_ms > 0:
            self.total_duration = duration_ms
            self.seek_slider.configure(to=self.total_duration)
            self.update_time_label()
            for seg in self.processor.segments_data:
                start_frac = seg["start_ms"] / duration_ms
                end_frac = seg["end_ms"] / duration_ms
                segments_info.append((start_frac, end_frac))
                
        self.draw_waveform(self.dub_canvas_frame, mix_data, '#ff7f0e', segments=segments_info) # Naranja

    def get_current_mix(self):
        if not self.processor or not self.processor.original_audio:
            return None
            
        final_orig = self.processor.original_audio
        final_dub = self.processor.dubbed_audio
        
        # Aplicar mute y volumen a la pista original
        if self.mute_original:
            final_orig = final_orig - 100 # Reducción extrema para silenciar
        else:
            vol = self.slider_vol_orig.get()
            if vol == 0:
                final_orig = final_orig - 100
            else:
                db_change = 20 * math.log10(vol)
                final_orig = final_orig + db_change
                
        # Aplicar mute y volumen a la pista doblada
        if not final_dub:
            return final_orig
            
        if self.mute_dubbed:
            final_dub = final_dub - 100
        else:
            vol = self.slider_vol_dub.get()
            if vol == 0:
                final_dub = final_dub - 100
            else:
                db_change = 20 * math.log10(vol)
                final_dub = final_dub + db_change
                
        return final_orig.overlay(final_dub)

    def export_audio(self):
        if not self.processor or not self.processor.dubbed_audio:
            messagebox.showwarning("Atención", "No hay proyecto cargado para exportar.")
            return
            
        save_path = filedialog.asksaveasfilename(
            defaultextension=".wav", 
            filetypes=[("WAV files", "*.wav"), ("MP3 files", "*.mp3")],
            title="Guardar mezcla final"
        )
        if not save_path: return
        
        final_mix = self.get_current_mix()
        if not final_mix: return
        
        format_ext = "mp3" if save_path.lower().endswith(".mp3") else "wav"
        
        try:
            final_mix.export(save_path, format=format_ext)
            messagebox.showinfo("Exportación Exitosa", f"Archivo guardado correctamente en:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error al exportar", f"Hubo un problema al exportar el archivo:\n{str(e)}")

    def play_audio(self, audio_segment, btn_widget, original_text, play_id, start_offset=0):
        self.stop_audio()
        self.playing_id = play_id
        self.play_start_offset = start_offset
        self.play_start_sys_time = time.time()
        
        temp_file = os.path.join(self.processor.temp_dir, "temp_play.wav")
        audio_segment.export(temp_file, format="wav")
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            self.play_process = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", temp_file],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=startupinfo
            )
            
            def check_process():
                if self.playing_id == play_id:
                    if play_id == "global" and not getattr(self, 'is_dragging', False):
                        current_time = self.play_start_offset + (time.time() - self.play_start_sys_time) * 1000
                        if current_time <= self.total_duration:
                            self.seek_slider.set(current_time)
                            self.update_time_label()
                            
                    if not hasattr(self, 'play_process') or self.play_process.poll() is not None:
                        try:
                            btn_widget.configure(text=original_text)
                        except tk.TclError:
                            pass
                        self.playing_id = None
                        if play_id == "global" and not getattr(self, 'is_dragging', False):
                            self.seek_slider.set(0)
                            self.update_time_label()
                    else:
                        self.after(50, check_process)
                        
            self.after(50, check_process)
        except FileNotFoundError:
            # Fallback a pydub nativo (bloqueante o asíncrono si está bien configurado)
            from pydub.playback import play
            import threading
            threading.Thread(target=play, args=(audio_segment,), daemon=True).start()
            self.playing_id = None

    def stop_audio(self):
        if hasattr(self, 'play_process') and self.play_process.poll() is None:
            self.play_process.terminate()
            self.play_process.wait()

    def toggle_play_global(self):
        if not self.processor or not self.processor.dubbed_audio:
            messagebox.showwarning("Atención", "No hay proyecto cargado para reproducir.")
            return

        if self.playing_id == "global":
            self.stop_audio()
            self.btn_play_global.configure(text="▶ Reproducir Mezcla")
            self.playing_id = None
            return

        mix = self.get_current_mix()
        if mix:
            start_ms = int(self.seek_slider.get())
            if start_ms >= len(mix):
                start_ms = 0
                self.seek_slider.set(0)
            audio_to_play = mix[start_ms:]
            self.btn_play_global.configure(text="⏹")
            self.play_audio(audio_to_play, self.btn_play_global, "▶ Reproducir Mezcla", "global", start_offset=start_ms)

    def toggle_play_segment(self, segment, btn_widget):
        seg_id = segment["id"]
        if self.playing_id == seg_id:
            self.stop_audio()
            btn_widget.configure(text="▶")
            self.playing_id = None
            return
            
        if not self.processor: return

        # 1. Obtener el trozo de audio original correspondiente al segmento
        original_slice = self.processor.original_audio[segment["start_ms"]:segment["end_ms"]]

        # 2. Obtener el segmento doblado ya procesado
        filename = segment["filename"]
        if filename in self.processor.processed_segments:
            dubbed_segment = self.processor.processed_segments[filename]
        else:
            # Si no se encuentra, usamos un segmento de silencio para no fallar
            dubbed_segment = AudioSegment.silent(duration=len(original_slice))

        # 3. Aplicar volumen y mute a ambos trozos, replicando la lógica de get_current_mix
        # A la pista original
        if self.mute_original:
            final_orig_slice = original_slice - 100
        else:
            vol = self.slider_vol_orig.get()
            db_change = 20 * math.log10(vol) if vol > 0 else -100
            final_orig_slice = original_slice + db_change

        # Al segmento doblado
        if self.mute_dubbed:
            final_dub_segment = dubbed_segment - 100
        else:
            vol = self.slider_vol_dub.get()
            db_change = 20 * math.log10(vol) if vol > 0 else -100
            final_dub_segment = dubbed_segment + db_change

        # 4. Mezclar los dos audios. El trozo original sirve de base para la duración.
        mixed_segment = final_orig_slice.overlay(final_dub_segment)

        # 5. Reproducir la mezcla del segmento
        btn_widget.configure(text="⏹")
        self.play_audio(mixed_segment, btn_widget, "▶", seg_id)

    def on_closing(self):
        self.stop_audio()
        if self.processor:
            self.processor.cleanup()
        self.destroy()
        self.quit()

if __name__ == "__main__":
    if not check_ffmpeg():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Dependencia faltante",
            "FFmpeg no está instalado o no se encuentra en el PATH del sistema.\n\n"
            "Esta aplicación requiere FFmpeg para realizar el time-stretching del audio.\n"
            "Por favor, instálalo desde https://ffmpeg.org/download.html y configúralo en las variables de entorno."
        )
        root.destroy()
        exit(1)
        
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = AppUI()
    app.mainloop()