import os
import subprocess
import shutil

class DirectQwenClient:
    """
    Cliente de inferencia directa para Qwen3-TTS en subproceso de Python (.venv).
    Elimina por completo la capa de red local HTTP/Gradio (Pinokio),
    ejecutándose a máxima velocidad local y liberando VRAM tras cada inferencia (--unload-after).
    """

    def __init__(
        self,
        python_exe: str = r"F:\Desarrollo\Qwen3TTS\.venv\Scripts\python.exe",
        engine_script: str = r"F:\Desarrollo\Qwen3TTS\src\infer_direct.py",
        base_url: str = "Direct Qwen3-TTS (Local)"
    ):
        self.python_exe = python_exe
        self.engine_script = engine_script
        self.base_url = base_url

    def check_connection(self, timeout: int = 2) -> bool:
        """Verifica si el intérprete y el script de inferencia directa de Qwen3-TTS existen."""
        return os.path.exists(self.python_exe) and os.path.exists(self.engine_script)

    def generate_voice_clone(
        self,
        ref_audio_path: str,
        ref_text: str,
        target_text: str,
        output_path: str,
        language: str = "English",
        model_size: str = "1.7B"
    ) -> str:
        """
        Invoca el motor de clonación de voz de Qwen3-TTS de forma directa en subproceso.
        Asegura limpieza de VRAM previa y posterior.
        """
        if not os.path.exists(ref_audio_path):
            raise FileNotFoundError(f"Audio de referencia no encontrado: {ref_audio_path}")

        if not self.check_connection():
            raise RuntimeError(
                f"No se encontró el ejecutable de Qwen3-TTS en '{self.python_exe}' o script en '{self.engine_script}'"
            )

        # Mapeo de idioma tolerante
        lang_map = {
            "en": "English",
            "english": "English",
            "pt": "Portuguese",
            "portuguese": "Portuguese",
            "es": "Spanish",
            "spanish": "Spanish"
        }
        resolved_lang = lang_map.get(str(language).lower(), language)

        # Selección de modelo
        model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
        if "0.6" in str(model_size):
            model_name = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        elif "custom" in str(model_size).lower():
            model_name = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
        elif "/" in str(model_size):
            model_name = model_size

        # Liberación preventiva de caché CUDA en el proceso padre si torch está cargado
        try:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = [
            self.python_exe,
            self.engine_script,
            "--model", model_name,
            "--prompt-audio", str(ref_audio_path),
            "--prompt-text", str(ref_text),
            "--text", str(target_text),
            "--language", str(resolved_lang),
            "--output", str(output_path),
            "--unload-after"
        ]

        # Asegurar codificación UTF-8 en Windows para caracteres especiales y acentos
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )

        if result.returncode != 0:
            err_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            raise RuntimeError(f"Error en Qwen3-TTS: {err_msg}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Qwen3-TTS finalizó pero el archivo de salida no fue generado: {output_path}")

        return output_path


# Alias para retrocompatibilidad total con código existente
PinokioClient = DirectQwenClient
