import os
import math
import subprocess
import tempfile
import shutil
import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_silence

class AudioProcessor:
    def __init__(self, original_audio_path, audios_dir, metadata):
        self.original_audio_path = original_audio_path
        self.audios_dir = audios_dir
        self.metadata = metadata or []

        self.original_audio = None
        self.processed_segments = {}
        self.dubbed_audio = None
        self._dubbed_mix_cache = None
        self._mix_is_dirty = True
        self.temp_dir = tempfile.mkdtemp()

        if self.original_audio_path and os.path.exists(self.original_audio_path):
            self.original_audio = AudioSegment.from_file(self.original_audio_path)
            self.recalculate_end_times()

        if self.audios_dir and os.path.exists(self.audios_dir):
            self.preload_segments()

    def recalculate_end_times(self):
        """Asegura orden cronológico y calcula end_ms solo si no está definido o es inválido."""
        if not self.metadata or self.original_audio is None:
            return

        for seg in self.metadata:
            if seg.get('start_ms') is None:
                seg['start_ms'] = 0

        self.metadata.sort(key=lambda x: x['start_ms'])
        total_len = len(self.original_audio)

        for i, seg in enumerate(self.metadata):
            cur_end = seg.get('end_ms')
            cur_start = seg.get('start_ms', 0)
            if cur_end is None or cur_end <= cur_start:
                if i < len(self.metadata) - 1:
                    next_s = self.metadata[i+1].get('start_ms', cur_start + 1000)
                    seg['end_ms'] = max(cur_start + 100, next_s)
                else:
                    seg['end_ms'] = total_len

    def process_segment(self, segment, manual_ratio=None):
        """
        Procesa el segmento de audio doblado:
        Aplica time-stretching con FFmpeg si excede la duración objetivo o si se especifica ratio manual.
        """
        filename = segment.get("filename", "")
        if not filename:
            return None, 1.0

        # Si el archivo activo ya existe en audios/ y no se solicita ratio manual explícito,
        # cargarlo directamente para mezcla instantánea y 100% fidedigna
        active_path = os.path.join(self.audios_dir, filename) if self.audios_dir else ""
        if active_path and os.path.exists(active_path) and manual_ratio is None:
            processed_audio = AudioSegment.from_file(active_path)
            self.processed_segments[filename] = processed_audio
            self.mark_mix_dirty()
            return processed_audio, segment.get("speed_ratio", 1.0)

        raw_path = os.path.join(self.audios_dir, "raw", filename) if self.audios_dir else ""
        if raw_path and os.path.exists(raw_path):
            source_filepath = raw_path
        else:
            source_filepath = active_path

        if not os.path.exists(source_filepath):
            return None, 1.0

        audio = AudioSegment.from_file(source_filepath)
        actual_duration = len(audio)
        target_duration = segment.get("end_ms", 0) - segment.get("start_ms", 0)

        ratio = 1.0
        if manual_ratio is not None:
            ratio = manual_ratio
        elif segment.get("is_manual_ratio") and segment.get("speed_ratio"):
            ratio = float(segment["speed_ratio"])
        elif target_duration > 0 and actual_duration > 0:
            raw_r = actual_duration / float(target_duration)
            if raw_r > 1.0:
                ratio = raw_r
            elif raw_r < 0.85:
                ratio = 0.85
            else:
                ratio = raw_r

        if abs(ratio - 1.0) >= 0.01:
            out_name = f"stretched_{ratio:.3f}_{filename}"
            out_path = os.path.join(self.temp_dir, out_name)
            if not os.path.exists(out_path) or os.path.getmtime(out_path) < os.path.getmtime(source_filepath):
                self._apply_atempo(source_filepath, out_path, ratio)
            processed_audio = AudioSegment.from_file(out_path)
        else:
            processed_audio = audio

        self.processed_segments[filename] = processed_audio
        self.mark_mix_dirty()
        return processed_audio, ratio

    def mark_mix_dirty(self):
        """Invalida la caché de la mezcla cuando los segmentos son alterados."""
        self._mix_is_dirty = True
        self._dubbed_mix_cache = None
        self.dubbed_audio = None

    def _apply_atempo(self, input_path, output_path, ratio):
        # Limitar ratio a valores válidos para ffmpeg atempo (0.5 a 100.0)
        ratio = max(0.5, min(ratio, 100.0))
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-filter:a", f"atempo={ratio}",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def preload_segments(self, audios_dir=None):
        """Precarga y procesa todos los segmentos cuyos audios existan en el directorio del proyecto."""
        if audios_dir:
            self.audios_dir = audios_dir
        if not self.audios_dir or not os.path.exists(self.audios_dir):
            return

        for seg in self.metadata:
            fname = seg.get("filename")
            if fname:
                fpath = os.path.join(self.audios_dir, fname)
                if os.path.exists(fpath):
                    try:
                        self.process_segment(seg)
                    except Exception as e:
                        print(f"[WARN] Error precargando segmento {fname}: {e}")

        self.mix_dubbed_audio()

    def mix_dubbed_audio(self, force=False):
        """Mezcla todos los segmentos doblados disponibles en sus posiciones temporales."""
        if not self.original_audio:
            return None

        if not force and not self._mix_is_dirty and self._dubbed_mix_cache is not None:
            return self._dubbed_mix_cache

        # Base silenciosa con frecuencia de muestreo y canales idénticos al original
        mix = AudioSegment.silent(
            duration=len(self.original_audio),
            frame_rate=self.original_audio.frame_rate
        ).set_channels(self.original_audio.channels)

        for seg in self.metadata:
            filename = seg.get("filename")
            if not filename:
                continue

            # Autocarga si el archivo existe en disco y aún no está en memoria procesado
            if filename not in self.processed_segments:
                fpath = os.path.join(self.audios_dir, filename) if self.audios_dir else ""
                if fpath and os.path.exists(fpath):
                    try:
                        self.process_segment(seg)
                    except Exception as e:
                        print(f"[WARN] Error cargando segmento en mix {filename}: {e}")

            if filename in self.processed_segments:
                seg_audio = self.processed_segments[filename]
                start_ms = seg.get("start_ms", 0)

                # Homogeneizar frecuencia de muestreo y canales antes del overlay
                if seg_audio.frame_rate != mix.frame_rate:
                    seg_audio = seg_audio.set_frame_rate(mix.frame_rate)
                if seg_audio.channels != mix.channels:
                    seg_audio = seg_audio.set_channels(mix.channels)

                mix = mix.overlay(seg_audio, position=start_ms)

        self.dubbed_audio = mix
        self._dubbed_mix_cache = mix
        self._mix_is_dirty = False
        return mix

    def get_slice_mix(self, start_ms=0, vol_orig=1.0, mute_orig=False, vol_dub=1.0, mute_dub=False):
        """Genera un fragmento de mezcla optimizado desde start_ms para reproducción instantánea."""
        if not self.original_audio:
            return None

        orig_slice = self.original_audio[start_ms:]

        if mute_orig or vol_orig == 0:
            final_orig = orig_slice - 100
        elif vol_orig != 1.0:
            db_change = 20 * math.log10(vol_orig)
            final_orig = orig_slice + db_change
        else:
            final_orig = orig_slice

        if not self.dubbed_audio or self._mix_is_dirty:
            self.mix_dubbed_audio()

        if not self.dubbed_audio:
            return final_orig

        dub_slice = self.dubbed_audio[start_ms:]

        if mute_dub or vol_dub == 0:
            final_dub = dub_slice - 100
        elif vol_dub != 1.0:
            db_change = 20 * math.log10(vol_dub)
            final_dub = dub_slice + db_change
        else:
            final_dub = dub_slice

        return final_orig.overlay(final_dub)

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

    def get_waveform_data(self, audio_segment, max_points=4000):
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
        """Exporta la mezcla actual a archivo de audio (.mp3 o .wav)."""
        final_mix = self.get_current_mix(vol_orig, mute_orig, vol_dub, mute_dub)
        if not final_mix:
            raise ValueError("No hay audio cargado para exportar.")

        ext = "wav" if save_path.lower().endswith(".wav") else "mp3"
        if ext == "mp3":
            final_mix.export(save_path, format="mp3", bitrate="320k")
        else:
            final_mix.export(save_path, format="wav")
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


def redistribute_segment_silence(source_audio_path: str, target_span_ms: int):
    """
    Redistribuye el silencio de un segmento bajo directrices inteligentes:
    1. Requiere silencio total > 2000 ms.
    2. Detecta pausas naturales reales (>= 500 ms), limitando a máximo 2 cortes (3 partes).
    3. Silencio intermedio acotado:
       - S_pausa = min(1500 ms, (silencio_total - reserva_minima) // K)
    4. Evaluación del residuo:
       - Si Residuo > 3000 ms: Mitad al inicio y mitad al final.
       - Si Residuo <= 3000 ms: Todo al final.
    """
    if not os.path.exists(source_audio_path):
        raise FileNotFoundError(f"Audio no encontrado: {source_audio_path}")

    audio = AudioSegment.from_file(source_audio_path)
    audio_len = len(audio)
    silencio_total_ms = target_span_ms - audio_len

    if silencio_total_ms <= 2000:
        raise ValueError(
            f"El segmento no tiene un silencio al final mayor a 2.0s ({silencio_total_ms/1000:.2f}s detectado). "
            "No requiere redistribución."
        )

    # 1. Detección de silencios con umbral de energía adaptativo
    thresh = max(audio.dBFS - 14.0, -42.0)
    MIN_PAUSE_MS = 500
    detected_ranges = detect_silence(audio, min_silence_len=MIN_PAUSE_MS, silence_thresh=thresh)

    # 2. Filtrar solo silencios internos (> 250ms de extremos y >= 500ms de duración)
    internal_pauses = [
        (s, e) for (s, e) in detected_ranges
        if s > 250 and e < (audio_len - 250) and (e - s) >= MIN_PAUSE_MS
    ]

    # Podar pausas muy juntas (mínimo 1000ms entre pausas)
    pruned_pauses = []
    for p in internal_pauses:
        if not pruned_pauses or (p[0] - pruned_pauses[-1][1]) >= 1000:
            pruned_pauses.append(p)

    k_pauses = len(pruned_pauses)

    # 3. Limitar a MÁXIMO 2 pausas (máximo 3 fragmentos de audio)
    if k_pauses > 2:
        pruned_pauses = sorted(pruned_pauses, key=lambda p: (p[1] - p[0]), reverse=True)[:2]
        pruned_pauses = sorted(pruned_pauses, key=lambda p: p[0])
        k_pauses = 2

    # 4. Cálculo de Silencios Intermedios (máximo 1500 ms por pausa)
    MAX_INTERMEDIATE_MS = 1500
    RESERVA_MINIMA_FINAL_MS = 800

    if k_pauses > 0:
        disponible_pausas = max(0, silencio_total_ms - RESERVA_MINIMA_FINAL_MS)
        silencio_por_pausa = min(MAX_INTERMEDIATE_MS, disponible_pausas // k_pauses)
        silencio_intermedio_total = silencio_por_pausa * k_pauses
    else:
        silencio_por_pausa = 0
        silencio_intermedio_total = 0

    # 5. Evaluación del Residuo
    residuo_ms = silencio_total_ms - silencio_intermedio_total

    if residuo_ms > 3000:
        # Partir en dos: mitad al inicio y mitad al final
        silencio_inicio_ms = residuo_ms // 2
        silencio_final_ms = residuo_ms - silencio_inicio_ms
    else:
        # Dejar todo el residuo al final
        silencio_inicio_ms = 0
        silencio_final_ms = residuo_ms

    # 6. Reconstrucción del Audio
    chunks = []

    # Agregar silencio inicial si aplica
    if silencio_inicio_ms > 0:
        chunks.append(
            AudioSegment.silent(duration=silencio_inicio_ms, frame_rate=audio.frame_rate).set_channels(audio.channels)
        )

    if k_pauses > 0 and silencio_por_pausa > 0:
        cut_points = [(s + e) // 2 for (s, e) in pruned_pauses]
        prev_idx = 0
        for cp in cut_points:
            chunks.append(audio[prev_idx:cp])
            chunks.append(
                AudioSegment.silent(duration=silencio_por_pausa, frame_rate=audio.frame_rate).set_channels(audio.channels)
            )
            prev_idx = cp
        chunks.append(audio[prev_idx:])
    else:
        chunks.append(audio)

    # Ensamblar
    rebuilt = chunks[0]
    for c in chunks[1:]:
        rebuilt += c

    info = {
        "mode": "smart_distribution",
        "k_pauses": k_pauses,
        "k_divisions": k_pauses + 1 if k_pauses > 0 else 1,
        "silence_added_per_pause_ms": silencio_por_pausa,
        "silence_start_ms": silencio_inicio_ms,
        "silence_end_ms": silencio_final_ms,
        "original_duration_ms": audio_len,
        "new_duration_ms": len(rebuilt),
        "target_span_ms": target_span_ms
    }
    return rebuilt, info

