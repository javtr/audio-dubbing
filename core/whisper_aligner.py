import gc
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

    def unload_model(self):
        """Descarga el modelo Whisper de la memoria y libera completamente la VRAM de la GPU."""
        if self._model is not None:
            try:
                del self._model
            except Exception:
                pass
            self._model = None
            print("[INFO Whisper] Modelo Whisper descargado.")

        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                print("[INFO Whisper] Memoria CUDA / VRAM liberada con éxito.")
        except Exception:
            pass

    def transcribe_to_plain_text(self, audio_path, callback_status=None):
        """Transcribe el audio original a un texto corrido en español."""
        if callback_status:
            callback_status("Iniciando transcripción del audio completo con Whisper...")
        
        try:
            model = self._get_model()
            segments, info = model.transcribe(audio_path, language="es", beam_size=5)
            
            full_text = []
            for s in segments:
                clean = s.text.strip()
                if clean:
                    full_text.append(clean)
                    
            return " ".join(full_text)
        finally:
            self.unload_model()

    def generate_gemini_prompt(self, spanish_text):
        """Genera el prompt listo para copiar y pegar en Gemini Web con directrices estrictas de conteo y balance de palabras (90%-110%)."""
        prompt = f"""Actúa como un director de doblaje profesional y traductor audiovisual experto en adaptación de guiones (Script Adaptation & Dubbing Localization).
A continuación tienes la transcripción en español de un video para ser doblado al inglés mediante clonación de voz por IA (TTS).

🎯 REGLA DE ORO: BALANCE Y CONTEO ESTRICTO DE PALABRAS (RANGO OBLIGATORIO: 90% A 110%)
En el doblaje por IA, la duración del audio sintetizado depende directamente de la cantidad de palabras:
- Si la adaptación tiene MENOS DEL 90% de palabras: El audio en inglés termina demasiado rápido, dejando vacíos incómodos de silencio en el video y perdiendo información valiosa.
- Si la adaptación tiene MÁS DEL 110% de palabras: El audio se ve obligado a acelerarse de manera artificial y excesiva, arruinando la dicción y la naturalidad del locutor.
- RANGO VÁLIDO Y OBLIGATORIO: La traducción en inglés DEBE tener entre el 90% y el 110% del número de palabras de la frase original en español. El sistema marcará como error cualquier segmento que quede por debajo del 90%.

📐 PROCEDIMIENTO OBLIGATORIO DE CONTEO Y CÁLCULO PARA CADA SEGMENTO:
Antes de redactar la versión final de cada fragmento, DEBES seguir este proceso:
1. Cuenta las palabras exactas de la frase en español (ejemplo: 40 palabras).
2. Calcula tu rango objetivo de palabras en inglés: mínimo 90% (36 palabras) y máximo 110% (44 palabras).
3. Redacta la adaptación en inglés y cuenta cuántas palabras obtuviste:
   - Si tu traducción en inglés quedó por debajo del 90% (< 36 palabras): ¡NO LA ENTREGUES ASÍ! Es demasiado corta. Amplía la redacción explicando con mayor detalle, utilizando vocabulario técnico preciso, oraciones completas y descripciones ricas sin perder el sentido.
   - Si tu traducción superó el 110% (> 44 palabras): Condensa levemente oraciones secundarias sin omitir datos esenciales.

⚠️ OTRAS REGLAS OBLIGATORIAS:
1. **NO RESUMAS NI OMITAS INFORMACIÓN:** No es un resumen. Debes traducir TODOS los conceptos, detalles, pasos técnicos, advertencias y matices expresados en el original.
2. **NO INFLES CON RELLENO ARTIFICIAL:** No uses muletillas vacías repetitivas. Usa inglés fluido, natural y descriptivo propio de un locutor nativo experto en la materia.
3. **Segmentación Coherente:** Cada fragmento debe representar una oración o idea completa con puntuación adecuada.
4. **Tono Emocional:** Asigna a cada fragmento uno de estos 4 tonos exactos según el contexto:
   - "Conversational": Tono casual, neutro, informal o introductorio.
   - "Explanatory": Tono didáctico, explicando conceptos técnicos o pasos con calma.
   - "Effusive": Tono enérgico, de advertencia, sorpresa, entusiasmo o énfasis marcado.
   - "Serious": Tono formal, conclusión analítica o advertencia de riesgo.

Devuelve ÚNICAMENTE un bloque de código JSON válido con esta estructura exacta (sin texto introductorio, ni despedidas, ni explicaciones adicionales):

[
  {{
    "id": "seg-0",
    "original": "<frase en español>",
    "translated": "<adaptación en inglés verificando que tenga entre el 90% y el 110% de palabras>",
    "tone": "Conversational",
    "filename": "segment_000.wav"
  }},
  {{
    "id": "seg-1",
    "original": "<frase en español>",
    "translated": "<adaptación en inglés verificando que tenga entre el 90% y el 110% de palabras>",
    "tone": "Explanatory",
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
        Utiliza emparejamiento por secuencias (N-Grams de 3 a 5 palabras) y garantías monótonas
        para evitar falsos positivos y asignaciones en 0 ms.
        """
        if not gemini_data:
            raise ValueError("La lista de secciones de Gemini está vacía.")

        try:
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
                            "start_ms": int(word.start * 1000),
                            "end_ms": int(word.end * 1000)
                        })

            if callback_status:
                callback_status("Alineando texto semántico con la pista de audio (N-Grams)...")

            current_search_idx = 0
            total_words = len(whisper_words)

            for i, item in enumerate(gemini_data):
                original_text = item.get("original", "")
                gem_words = [w for w in re.sub(r'[^\w\s]', '', original_text.lower()).strip().split() if w]
                word_count = len(gem_words)

                best_match_idx = -1
                best_score = 0
                target_len = min(4, word_count) if word_count > 0 else 0

                if target_len > 0 and total_words > 0:
                    # Búsqueda en ventana hacia adelante (evita saltos absurdos de varios minutos)
                    search_limit = min(current_search_idx + 150, total_words - target_len + 1)
                    target_slice = gem_words[:target_len]

                    for k in range(current_search_idx, search_limit):
                        score = sum(1 for w_off, gw in enumerate(target_slice) if whisper_words[k + w_off]["word"] == gw)
                        if score > best_score:
                            best_score = score
                            best_match_idx = k
                            if score == target_len:
                                break  # Coincidencia perfecta de la secuencia

                # Criterio de aceptación: al menos 2 palabras consecutivas si target >= 2, o 1 si la frase tiene 1
                min_acceptable_score = min(2, target_len) if target_len > 0 else 1
                if best_match_idx != -1 and best_score >= min_acceptable_score:
                    start_ms = whisper_words[best_match_idx]["start_ms"]
                    # Avanzar el puntero de búsqueda seguro (sin sobrepasar el inicio del siguiente segmento)
                    current_search_idx = best_match_idx + min(target_len, 3)
                else:
                    # Fallback seguro: no saltar al inicio ni romper el flujo
                    if i == 0:
                        start_ms = 0
                    else:
                        prev_start = gemini_data[i-1].get("start_ms", 0)
                        if current_search_idx < total_words:
                            candidate_ms = whisper_words[current_search_idx]["start_ms"]
                            start_ms = candidate_ms if candidate_ms >= prev_start else prev_start + 200
                        else:
                            start_ms = prev_start + 500

                # Regla de oro 1: El primer segmento siempre arranca en 0 ms
                if i == 0:
                    start_ms = 0
                else:
                    # Regla de oro 2: Garantía monótona estricta (ningún segmento intermedio puede ser menor al anterior)
                    prev_start = gemini_data[i-1].get("start_ms", 0)
                    if start_ms <= prev_start:
                        start_ms = prev_start + 100

                item["start_ms"] = start_ms
                item["orig_start_ms"] = start_ms

            # Asignar end_ms basándose en el inicio del siguiente segmento
            for i in range(len(gemini_data)):
                if i < len(gemini_data) - 1:
                    next_start = gemini_data[i+1].get("start_ms")
                    gemini_data[i]["end_ms"] = next_start if next_start is not None else audio_duration_ms
                else:
                    gemini_data[i]["end_ms"] = audio_duration_ms

                # Guardar ancla de fin original fija
                gemini_data[i]["orig_end_ms"] = gemini_data[i]["end_ms"]

                # Asegurar nombre de archivo
                if "filename" not in gemini_data[i] or not gemini_data[i]["filename"]:
                    gemini_data[i]["filename"] = f"segment_{i:03d}.wav"

            return gemini_data, audio_duration_ms
        finally:
            self.unload_model()
