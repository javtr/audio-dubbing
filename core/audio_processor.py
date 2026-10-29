import os
import math
import json
import time
import subprocess
import tempfile
import shutil
import numpy as np
import soundfile as sf
import scipy.signal as signal
from pydub import AudioSegment
from pydub.silence import detect_silence


class FastDubMixer:
    """
    Mezclador vectorial de audio ultrarrápido con soundfile y NumPy.
    Reemplaza los bucles lentos de pydub.overlay() para proyectos de cualquier duración (+50 o +90 segmentos),
    reduciendo el tiempo de mezcla de 90 segundos a solo 300-600 milisegundos.
    Calcula simultáneamente los picos de onda (waveform_dub.json) y genera el archivo WAV versionado para streaming.
    """
    _SEGMENT_CACHE = {}  # fpath -> (mtime, target_sr, target_ch, data_array)

    @classmethod
    def clear_cache(cls):
        cls._SEGMENT_CACHE.clear()

    @classmethod
    def mix_project(cls, paths: dict, project: str, metadata: list, points: int = 1600) -> tuple[str, list, int]:
        orig_path = paths.get("audio_file")
        audios_dir = paths.get("audios_dir")
        root_dir = paths.get("root")

        if not orig_path or not os.path.exists(orig_path):
            return "", [], 0

        info = sf.info(orig_path)
        sample_rate = info.samplerate
        channels = info.channels
        total_frames = info.frames
        dur_ms = int(info.duration * 1000)

        mix_buffer = np.zeros((total_frames, channels), dtype=np.float32)

        for seg in metadata:
            fname = seg.get("filename")
            if not fname:
                continue
            fpath = os.path.join(audios_dir, fname) if audios_dir else ""
            if not fpath or not os.path.exists(fpath):
                continue

            try:
                mtime = os.path.getmtime(fpath)
                cached = cls._SEGMENT_CACHE.get(fpath)
                if (cached is not None and 
                    cached[0] == mtime and 
                    cached[1] == sample_rate and 
                    cached[2] == channels):
                    data = cached[3]
                else:
                    data, sr = sf.read(fpath, dtype='float32')
                    if sr != sample_rate:
                        gcd = math.gcd(sample_rate, sr)
                        up = sample_rate // gcd
                        down = sr // gcd
                        data = signal.resample_poly(data, up, down)
                    if data.ndim == 1 and channels == 2:
                        data = np.column_stack((data, data))
                    elif data.ndim == 2 and data.shape[1] == 1 and channels == 2:
                        data = np.repeat(data, 2, axis=1)
                    cls._SEGMENT_CACHE[fpath] = (mtime, sample_rate, channels, data)

                start_ms = seg.get("start_ms", 0)
                start_frame = int(start_ms * sample_rate / 1000)
                end_frame = min(total_frames, start_frame + len(data))
                if end_frame > start_frame:
                    mix_buffer[start_frame:end_frame] = data[:end_frame - start_frame]
            except Exception as e:
                print(f"[FastDubMixer] Error cargando segmento {fname}: {e}")

        # Cálculo directo de picos de onda min/max en memoria (~100 ms)
        peaks = []
        if points > 0 and total_frames >= points:
            samples_per_bin = total_frames // points
            mono = mix_buffer[:, 0] if channels > 1 else mix_buffer.flatten()
            trimmed = mono[:points * samples_per_bin].reshape(points, samples_per_bin)
            mins = np.min(trimmed, axis=1)
            maxs = np.max(trimmed, axis=1)
            peak_val = max(float(np.max(np.abs(mins))), float(np.max(np.abs(maxs))))
            if peak_val > 0.001:
                mins /= peak_val
                maxs /= peak_val
            interleaved = np.empty(points * 2, dtype=np.float32)
            interleaved[0::2] = mins
            interleaved[1::2] = maxs
            peaks = np.round(interleaved, 3).tolist()

        # Guardar waveform_dub.json inmediatamente en disco para que /api/waveform responda en 1ms
        dub_wave_file = paths.get("waveform_dub_file") or os.path.join(root_dir, "waveform_dub.json")
        meta_mtime = time.time()
        meta_file = paths.get("metadata_file")
        if meta_file and os.path.exists(meta_file):
            meta_mtime = os.path.getmtime(meta_file)

        now_t = time.time()
        try:
            with open(dub_wave_file, "w", encoding="utf-8") as f:
                json.dump({
                    "metadata_mtime": meta_mtime,
                    "wav_mtime": now_t,
                    "duration_ms": dur_ms,
                    "points": points,
                    "peaks": peaks
                }, f)
        except Exception as e:
            print(f"[FastDubMixer] Error guardando waveform_dub.json: {e}")

        # Exportar mezcla WAV versionada (0.3s)
        mix_dir = os.path.join(root_dir, "mix")
        os.makedirs(mix_dir, exist_ok=True)
        timestamp = int(now_t * 1000)
        new_filename = f"dubbed_mix_{timestamp}.wav"
        new_filepath = os.path.join(mix_dir, new_filename)

        try:
            sf.write(new_filepath, mix_buffer, sample_rate, subtype='PCM_16')
            # Limpieza oportunista de versiones de mezcla anteriores
            for f in os.listdir(mix_dir):
                if f != new_filename and f.startswith("dubbed_mix"):
                    try:
                        os.remove(os.path.join(mix_dir, f))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[FastDubMixer] Error escribiendo archivo WAV de mezcla: {e}")

        return new_filepath, peaks, dur_ms

class AudioProcessor:
    def __init__(self, original_audio_path, audios_dir, metadata, lazy=True):
        self.original_audio_path = original_audio_path
        self.audios_dir = audios_dir
        self.metadata = metadata or []

        self._original_audio = None
        self.processed_segments = {}
        self.dubbed_audio = None
        self._dubbed_mix_cache = None
        self._mix_is_dirty = True
        self.temp_dir = tempfile.mkdtemp()
        self.duration_ms = 0
        self.sample_rate = 44100
        self.channels = 2

        # Lectura ultrarrápida de duración y formato con soundfile (1 ms sin cargar datos a RAM)
        if self.original_audio_path and os.path.exists(self.original_audio_path):
            try:
                info = sf.info(self.original_audio_path)
                self.duration_ms = int(info.duration * 1000)
                self.sample_rate = info.samplerate
                self.channels = info.channels
            except Exception:
                pass
            self.recalculate_end_times()

        if not lazy:
            if self.original_audio_path and os.path.exists(self.original_audio_path):
                _ = self.original_audio
            if self.audios_dir and os.path.exists(self.audios_dir):
                self.preload_segments()

    @property
    def original_audio(self):
        """Carga pydub AudioSegment bajo demanda solo si es estrictamente necesario."""
        if self._original_audio is None and self.original_audio_path and os.path.exists(self.original_audio_path):
            self._original_audio = AudioSegment.from_file(self.original_audio_path)
        return self._original_audio

    @original_audio.setter
    def original_audio(self, val):
        self._original_audio = val

    def recalculate_end_times(self):
        """Asegura orden cronológico y calcula end_ms solo si no está definido o es inválido."""
        if not self.metadata:
            return

        for seg in self.metadata:
            if seg.get('start_ms') is None:
                seg['start_ms'] = 0

        self.metadata.sort(key=lambda x: x['start_ms'])
        total_len = self.duration_ms or (len(self.original_audio) if self.original_audio_path and os.path.exists(self.original_audio_path) else 10000)

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
            elif raw_r < 0.87:
                ratio = 0.87
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
        """Mezcla vectorial rápida de todos los segmentos doblados usando FastDubMixer."""
        if not self.original_audio_path or not os.path.exists(self.original_audio_path):
            return None

        if not force and not self._mix_is_dirty and self._dubbed_mix_cache is not None:
            return self._dubbed_mix_cache

        paths = {
            "audio_file": self.original_audio_path,
            "audios_dir": self.audios_dir,
            "root": os.path.dirname(self.audios_dir) if self.audios_dir else "."
        }
        mix_file, peaks, dur_ms = FastDubMixer.mix_project(paths, "temp", self.metadata)
        if mix_file and os.path.exists(mix_file):
            try:
                mix_seg = AudioSegment.from_file(mix_file)
                self.dubbed_audio = mix_seg
                self._dubbed_mix_cache = mix_seg
                self._mix_is_dirty = False
                return mix_seg
            except Exception as e:
                print(f"[AudioProcessor] Error cargando AudioSegment desde mix WAV: {e}")

        return None

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

