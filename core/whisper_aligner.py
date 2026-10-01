import re
from faster_whisper import WhisperModel

class WhisperAligner:
    def __init__(self, model_size="small"):
        self.model_size = model_size
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                self._model = WhisperModel(self.model_size, device="cuda", compute_type="float16")
                print("[INFO Whisper] Modelo cargado en GPU (CUDA)")
            except Exception as e:
                print(f"[WARN Whisper] CUDA no disponible ({e}), usando CPU int8")
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_to_plain_text(self, audio_path, callback_status=None):
        """Transcribe el audio original a un texto corrido en español."""
        if callback_status:
            callback_status("Iniciando transcripción del audio completo con Whisper...")
        
        model = self._get_model()
        segments, info = model.transcribe(audio_path, language="es", beam_size=5)
        
        full_text = []
        for s in segments:
            clean = s.text.strip()
            if clean:
                full_text.append(clean)
                
        return " ".join(full_text)

    def generate_gemini_prompt(self, spanish_text):
        """Genera el prompt listo para copiar y pegar en Gemini Web."""
        prompt = f"""Actúa como un director de doblaje profesional y traductor audiovisual experto.
A continuación tienes la transcripción completa de un video en español.

Instrucciones:
1. Divide el texto en oraciones o fragmentos lógicos completos y con sentido natural para doblaje (no dejes frases cortadas a la mitad).
2. Traduce cada frase al inglés con fluidez y naturalidad (evita traducciones literales o acartonadas).
3. Asigna a cada frase uno de los siguientes 4 tonos exactos según el contexto emocional:
   - "Conversational" (Tono natural, neutro, informal o de charla)
   - "Explanatory" (Tono didáctico, explicando conceptos, pausado)
   - "Effusive" (Tono enérgico, de advertencia, sorpresa, entusiasmo o énfasis marcado)
   - "Serious" (Tono formal, conclusión importante o punto clave)
4. Devuelve ÚNICAMENTE un bloque de código JSON válido con esta estructura exacta (sin texto introductorio ni explicaciones adicionales):

[
  {{
    "id": "seg-0",
    "original": "<frase en español>",
    "translated": "<traducción fluida al inglés>",
    "tone": "Serious",
    "filename": "segment_000.wav"
  }},
  {{
    "id": "seg-1",
    "original": "<frase en español>",
    "translated": "<traducción fluida al inglés>",
    "tone": "Conversational",
    "filename": "segment_001.wav"
  }}
]

--- GUION ORIGINAL EN ESPAÑOL ---
{spanish_text}
"""
        return prompt

    def align_timestamps(self, audio_path, gemini_data, callback_status=None):
        """
        Alinea el JSON de Gemini con los timestamps reales por palabra usando Whisper.
        Actualiza y retorna gemini_data con los campos 'start_ms' y 'end_ms'.
        """
        if not gemini_data:
            raise ValueError("La lista de secciones de Gemini está vacía.")

        if callback_status:
            callback_status("Extrayendo timestamps por palabra con Whisper...")

        model = self._get_model()
        segments, info = model.transcribe(audio_path, language="es", beam_size=5, word_timestamps=True)
        audio_duration_ms = int(info.duration * 1000)

        # Aplanar todas las palabras transcritas con su timestamp
        whisper_words = []
        for seg in segments:
            for word in seg.words:
                clean_word = re.sub(r'[^\w\s]', '', word.word.lower()).strip()
                if clean_word:
                    whisper_words.append({
                        "word": clean_word,
                        "start_ms": int(word.start * 1000)
                    })

        if callback_status:
            callback_status("Alineando texto semántico con la pista de audio...")

        search_index = 0
        for i, item in enumerate(gemini_data):
            original_text = item.get("original", "")
            gem_words = re.sub(r'[^\w\s]', '', original_text.lower()).strip().split()
            word_count = len(gem_words)

            matched = False
            if gem_words:
                # Buscamos coincidencias con las primeras 3 palabras
                for g_word in gem_words[:3]:
                    if matched:
                        break
                    limit = min(search_index + 100, len(whisper_words))
                    for j in range(search_index, limit):
                        if whisper_words[j]["word"] == g_word:
                            item["start_ms"] = whisper_words[j]["start_ms"]
                            jump = max(1, word_count - 3)
                            search_index = j + jump
                            matched = True
                            break

            if not matched:
                print(f"[WARN] No se pudo alinear exactamente: {item.get('id', i)}")
                if search_index < len(whisper_words):
                    item["start_ms"] = whisper_words[search_index]["start_ms"]
                elif i > 0:
                    item["start_ms"] = gemini_data[i-1].get("end_ms", 0)
                else:
                    item["start_ms"] = 0

            # Regla de oro: El primer segmento siempre arranca en 0 ms
            if i == 0:
                item["start_ms"] = 0

        # Asignar end_ms basándose en el inicio del siguiente segmento
        for i in range(len(gemini_data)):
            if i < len(gemini_data) - 1:
                next_start = gemini_data[i+1].get("start_ms")
                gemini_data[i]["end_ms"] = next_start if next_start is not None else audio_duration_ms
            else:
                gemini_data[i]["end_ms"] = audio_duration_ms

            # Asegurar nombre de archivo
            if "filename" not in gemini_data[i] or not gemini_data[i]["filename"]:
                gemini_data[i]["filename"] = f"segment_{i:03d}.wav"

        return gemini_data, audio_duration_ms
