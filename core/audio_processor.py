import os
import math
import subprocess
import tempfile
import shutil
import numpy as np
from pydub import AudioSegment

class AudioProcessor:
    def __init__(self, original_audio_path, audios_dir, metadata):
        self.original_audio_path = original_audio_path
        self.audios_dir = audios_dir
        self.metadata = metadata or []

        self.original_audio = None
        self.processed_segments = {}
        self.dubbed_audio = None
        self.temp_dir = tempfile.mkdtemp()

        if self.original_audio_path and os.path.exists(self.original_audio_path):
            self.original_audio = AudioSegment.from_file(self.original_audio_path)
            self.recalculate_end_times()

    def recalculate_end_times(self):
        """Asegura orden cronológico y calcula end_ms si no está definido."""
        if not self.metadata or self.original_audio is None:
            return

        for seg in self.metadata:
            if seg.get('start_ms') is None:
                seg['start_ms'] = 0

        self.metadata.sort(key=lambda x: x['start_ms'])
        total_len = len(self.original_audio)

        for i in range(len(self.metadata) - 1):
            self.metadata[i]['end_ms'] = self.metadata[i+1]['start_ms']

        if self.metadata:
            self.metadata[-1]['end_ms'] = total_len

    def process_segment(self, segment, manual_ratio=None):
        """
        Procesa el segmento de audio doblado:
        Aplica time-stretching con FFmpeg si excede la duración objetivo o si se especifica ratio manual.
        """
        filename = segment["filename"]
        filepath = os.path.join(self.audios_dir, filename)

        if not os.path.exists(filepath):
            return None, 1.0

        audio = AudioSegment.from_file(filepath)
        actual_duration = len(audio)
        target_duration = segment.get("end_ms", 0) - segment.get("start_ms", 0)

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
        # Limitar ratio a valores válidos para ffmpeg atempo (0.5 a 100.0)
        ratio = max(0.5, min(ratio, 100.0))
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-filter:a", f"atempo={ratio}",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def mix_dubbed_audio(self):
        """Mezcla todos los segmentos doblados disponibles en sus posiciones temporales."""
        if not self.original_audio:
            return None

        mix = AudioSegment.silent(duration=len(self.original_audio))
        for seg in self.metadata:
            filename = seg.get("filename")
            if filename in self.processed_segments:
                seg_audio = self.processed_segments[filename]
                start_ms = seg.get("start_ms", 0)
                mix = mix.overlay(seg_audio, position=start_ms)

        self.dubbed_audio = mix
        return mix

    def get_current_mix(self, vol_orig=1.0, mute_orig=False, vol_dub=1.0, mute_dub=False):
        """Genera la mezcla combinada aplicando volumen y silenciamiento."""
        if not self.original_audio:
            return None

        # Pista original
        if mute_orig or vol_orig == 0:
            final_orig = self.original_audio - 100
        else:
            db_change = 20 * math.log10(vol_orig)
            final_orig = self.original_audio + db_change

        if not self.dubbed_audio:
            self.mix_dubbed_audio()

        if not self.dubbed_audio:
            return final_orig

        # Pista doblada
        if mute_dub or vol_dub == 0:
            final_dub = self.dubbed_audio - 100
        else:
            db_change = 20 * math.log10(vol_dub)
            final_dub = self.dubbed_audio + db_change

        return final_orig.overlay(final_dub)

    def get_waveform_data(self, audio_segment, max_points=1000):
        """Genera datos de muestras normalizados para renderizar ondas en matplotlib."""
        if not audio_segment:
            return np.zeros(100)

        samples = np.array(audio_segment.get_array_of_samples())
        if audio_segment.channels == 2:
            samples = samples[::2]
        if len(samples) > max_points:
            factor = max(1, len(samples) // max_points)
            samples = samples[::factor]
        return samples

    def export_mix_audio(self, save_path, vol_orig=1.0, mute_orig=False, vol_dub=1.0, mute_dub=False):
        """Exporta la mezcla actual a archivo de audio (.wav o .mp3)."""
        final_mix = self.get_current_mix(vol_orig, mute_orig, vol_dub, mute_dub)
        if not final_mix:
            raise ValueError("No hay audio cargado para exportar.")

        ext = "mp3" if save_path.lower().endswith(".mp3") else "wav"
        final_mix.export(save_path, format=ext)
        return save_path

    def export_video_with_audio(self, video_path, audio_path, output_video_path):
        """Combina el video original con el nuevo audio doblado sin recodificar el video."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video original no encontrado: {video_path}")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio final no encontrado: {audio_path}")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_video_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_video_path

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
