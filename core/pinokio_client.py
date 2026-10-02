import os
import shutil
import urllib.request
from gradio_client import Client, handle_file

class PinokioClient:
    def __init__(self, base_url="http://127.0.0.1:7860"):
        self.base_url = base_url.rstrip("/")
        self._client = None

    def check_connection(self, timeout=2):
        """Verifica si el servidor de Pinokio/Gradio está respondiendo."""
        try:
            req = urllib.request.Request(self.base_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status in (200, 302, 404)
        except Exception:
            return False

    def _get_client(self):
        if self._client is None:
            self._client = Client(self.base_url)
        return self._client

    def generate_voice_clone(self, ref_audio_path, ref_text, target_text, output_path, language="English", model_size="1.7B"):
        """
        Envía la solicitud de clonación de voz a TTS vía Gradio en Pinokio.
        Guarda el audio generado en output_path.
        """
        if not os.path.exists(ref_audio_path):
            raise FileNotFoundError(f"Audio de referencia no encontrado: {ref_audio_path}")

        lang_map = {
            "en": "English",
            "english": "English",
            "pt": "Portuguese",
            "portuguese": "Portuguese",
            "es": "Spanish",
            "spanish": "Spanish"
        }
        resolved_lang = lang_map.get(str(language).lower(), language)

        client = self._get_client()

        result = client.predict(
            ref_audio=handle_file(ref_audio_path),
            ref_text=ref_text,
            target_text=target_text,
            language=resolved_lang,
            use_xvector_only=False,
            model_size=model_size,
            max_chunk_chars=200,
            chunk_gap=0.0,
            seed=-1,
            api_name="/generate_voice_clone"
        )

        temp_audio_path = result[0]
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_audio_path, output_path)
        return output_path
