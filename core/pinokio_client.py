import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

class DirectQwenClient:
    """
    Cliente de inferencia de alto rendimiento para Qwen3-TTS.
    Se comunica con un servidor local persistente (http://127.0.0.1:7865) ejecutado en el
    entorno .venv dedicado de Qwen3TTS. Mantiene el modelo cargado en VRAM para síntesis
    ultrarrápida y permite montarlo/desmontarlo a voluntad mediante el botón de la interfaz.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7865",
        python_exe: str = r"F:\Desarrollo\Qwen3TTS\.venv\Scripts\python.exe",
        server_script: str = r"F:\Desarrollo\Qwen3TTS\server.py",
        default_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    ):
        self.base_url = base_url.rstrip("/")
        self.python_exe = python_exe
        self.server_script = server_script
        self.default_model = default_model
        self._server_proc: Optional[subprocess.Popen] = None

    def is_engine_installed(self) -> bool:
        """Verifica si los archivos locales del motor Qwen3-TTS existen."""
        return os.path.exists(self.python_exe) and os.path.exists(self.server_script)

    def is_server_alive(self) -> bool:
        """Verifica si el servidor HTTP local está respondiendo."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=1.0) as res:
                return res.status == 200
        except Exception:
            return False

    def check_connection(self, timeout: int = 2) -> bool:
        """Comprueba disponibilidad del servidor o capacidad para iniciarlo."""
        if self.is_server_alive():
            return True
        return self.is_engine_installed()

    def ensure_server_running(self, timeout_sec: int = 8) -> bool:
        """Inicia el servidor local en segundo plano si aún no está en ejecución."""
        if self.is_server_alive():
            return True

        if not self.is_engine_installed():
            raise FileNotFoundError(
                f"No se encontró el entorno de Qwen3-TTS en '{self.python_exe}' o script en '{self.server_script}'"
            )

        print(f"[QwenClient] Iniciando servidor local Qwen3-TTS en {self.base_url}...")
        creation_flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        self._server_proc = subprocess.Popen(
            [self.python_exe, self.server_script, "--port", "7865"],
            creationflags=creation_flags,
            env=env
        )

        start_t = time.time()
        while time.time() - start_t < timeout_sec:
            if self.is_server_alive():
                print(f"[QwenClient] Servidor Qwen3-TTS listo (PID: {self._server_proc.pid})")
                return True
            time.sleep(0.4)

        raise TimeoutError(f"El servidor de Qwen3-TTS no respondió tras {timeout_sec}s.")

    def get_status(self) -> Dict[str, Any]:
        """Consulta el estado del modelo y VRAM del servidor local."""
        if self.is_server_alive():
            try:
                req = urllib.request.Request(f"{self.base_url}/status")
                with urllib.request.urlopen(req, timeout=1.5) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    return {
                        "connected": True,
                        "server_online": True,
                        "model_loaded": data.get("model_loaded", False),
                        "model_name": data.get("model_name", self.default_model),
                        "free_vram_gb": data.get("free_vram_gb", 0.0),
                        "total_vram_gb": data.get("total_vram_gb", 0.0),
                        "url": self.base_url
                    }
            except Exception:
                pass

        installed = self.is_engine_installed()
        return {
            "connected": installed,
            "server_online": False,
            "model_loaded": False,
            "model_name": self.default_model,
            "free_vram_gb": 0.0,
            "total_vram_gb": 0.0,
            "url": self.base_url
        }

    def load_model(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Carga el modelo en la VRAM de la GPU y lo deja residente listo para sintetizar."""
        self.ensure_server_running()
        target_model = model_name or self.default_model

        payload = json.dumps({"model_name": target_model}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/load_model",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        print(f"[QwenClient] Montando modelo '{target_model}' en VRAM de GPU...")
        with urllib.request.urlopen(req, timeout=45) as res:
            data = json.loads(res.read().decode("utf-8"))
            print(f"[QwenClient] Modelo montado con éxito: {data}")
            return data

    def unload_model(self) -> Dict[str, Any]:
        """Descarga el modelo de la VRAM y purga la memoria CUDA."""
        if not self.is_server_alive():
            return {"status": "unloaded", "model_loaded": False}

        req = urllib.request.Request(
            f"{self.base_url}/unload_model",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        print("[QwenClient] Desmontando modelo de VRAM...")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))
                print(f"[QwenClient] VRAM liberada: {data}")
                return data
        except Exception as e:
            print(f"[QwenClient] Error al desmontar modelo: {e}")
            return {"status": "error", "detail": str(e)}

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
        Sintetiza la clonación de voz a través del servidor persistente con el modelo en VRAM.
        """
        if not os.path.exists(ref_audio_path):
            raise FileNotFoundError(f"Audio de referencia no encontrado: {ref_audio_path}")

        self.ensure_server_running()

        lang_map = {
            "en": "English",
            "english": "English",
            "pt": "Portuguese",
            "portuguese": "Portuguese",
            "es": "Spanish",
            "spanish": "Spanish"
        }
        resolved_lang = lang_map.get(str(language).lower(), language)

        model_name = self.default_model
        if "0.6" in str(model_size):
            model_name = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        elif "custom" in str(model_size).lower():
            model_name = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
        elif "/" in str(model_size):
            model_name = model_size

        payload = json.dumps({
            "text": target_text,
            "language": resolved_lang,
            "prompt_audio": os.path.abspath(ref_audio_path),
            "prompt_text": ref_text,
            "output_path": os.path.abspath(output_path),
            "model_name": model_name
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/synthesize",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                data = json.loads(res.read().decode("utf-8"))
                latency = data.get("latency_seconds", 0)
                dur = data.get("audio_duration_seconds", 0)
                print(f"[QwenClient] Audio generado: {dur}s sintetizados en {latency}s")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Error en servidor Qwen3-TTS ({e.code}): {err_body}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"No se generó el archivo de audio de salida: {output_path}")

        return output_path


# Alias para retrocompatibilidad total con el código existente
PinokioClient = DirectQwenClient
