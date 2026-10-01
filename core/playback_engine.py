import os
import time
import subprocess
import threading
import tempfile
from pydub import AudioSegment

class PlaybackEngine:
    """Motor de reproducción de audio desacoplado que utiliza ffplay con fallback seguro."""

    def __init__(self, temp_dir=None):
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.playing_process = None
        self.playing_id = None
        self.play_start_offset = 0
        self.play_start_sys_time = 0.0
        self._stop_event = threading.Event()

    def play_audio(self, audio_segment, play_id="global", start_offset=0, on_tick=None, on_finished=None):
        """
        Reproduce un AudioSegment usando ffplay de forma asíncrona.
        :param audio_segment: AudioSegment a reproducir.
        :param play_id: Identificador de la reproducción ("global", id de segmento, etc.).
        :param start_offset: Milisegundos de offset inicial para el cálculo de elapsed_ms.
        :param on_tick: Callback(elapsed_ms) invocado en cada intervalo de tiempo.
        :param on_finished: Callback() invocado al terminar la reproducción.
        """
        self.stop()
        self._stop_event.clear()
        self.playing_id = play_id
        self.play_start_offset = start_offset
        self.play_start_sys_time = time.time()

        temp_wav = os.path.join(self.temp_dir, f"playback_{os.getpid()}_{int(time.time() * 1000)}.wav")
        try:
            audio_segment.export(temp_wav, format="wav")
        except Exception as e:
            print(f"[PlaybackEngine] Error exportando audio temporal: {e}")
            if on_finished:
                on_finished()
            return

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            self.playing_process = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", temp_wav],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo
            )

            def _poll_worker():
                while not self._stop_event.is_set():
                    if self.playing_process is None:
                        break
                    ret = self.playing_process.poll()
                    if ret is not None:
                        # Proceso terminado
                        break
                    
                    if on_tick:
                        elapsed = self.play_start_offset + (time.time() - self.play_start_sys_time) * 1000
                        try:
                            on_tick(elapsed)
                        except Exception as e:
                            print(f"[PlaybackEngine on_tick error] {e}")

                    time.sleep(0.04)

                self.stop()
                try:
                    if os.path.exists(temp_wav):
                        os.remove(temp_wav)
                except Exception:
                    pass

                if on_finished:
                    try:
                        on_finished()
                    except Exception as e:
                        print(f"[PlaybackEngine on_finished error] {e}")

            threading.Thread(target=_poll_worker, daemon=True).start()

        except Exception as e:
            print(f"[PlaybackEngine] ffplay no disponible ({e}), usando fallback pydub.playback")
            try:
                from pydub.playback import play
                def _fallback_worker():
                    play(audio_segment)
                    self.playing_id = None
                    if on_finished:
                        on_finished()
                threading.Thread(target=_fallback_worker, daemon=True).start()
            except Exception as e2:
                print(f"[PlaybackEngine Fallback error] {e2}")
                self.playing_id = None
                if on_finished:
                    on_finished()

    def stop(self):
        """Detiene inmediatamente la reproducción actual."""
        self._stop_event.set()
        if self.playing_process and self.playing_process.poll() is None:
            try:
                self.playing_process.terminate()
                self.playing_process.wait(timeout=0.5)
            except Exception:
                try:
                    self.playing_process.kill()
                except Exception:
                    pass
        self.playing_process = None
        self.playing_id = None

    def is_playing(self):
        """Retorna True si hay audio reproduciéndose actualmente."""
        return self.playing_id is not None and self.playing_process is not None and self.playing_process.poll() is None

    def get_playing_id(self):
        return self.playing_id
