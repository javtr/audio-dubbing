import gc
import re
import unicodedata
from difflib import SequenceMatcher
from faster_whisper import WhisperModel

def normalize_token(text):
    """
    Elimina tildes, signos de puntuación y pasa a minúsculas para comparación robusta.
    Ej: 'aquí,' -> 'aqui', 'está!' -> 'esta'
    """
    if not text:
        return ""
    normalized = unicodedata.normalize('NFD', text.lower())
    without_accents = "".join(c for c in normalized if unicodedata.category(c) != 'Mn')
    clean = re.sub(r'[^\w\s]', '', without_accents).strip()
    return clean

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

    def generate_gemini_prompt(self, spanish_text, target_lang="en"):
        """Genera el prompt listo para copiar y pegar en Gemini Web según el idioma destino ('en' o 'pt')."""
        if str(target_lang).lower() in ("pt", "portuguese"):
            return self._build_portuguese_prompt(spanish_text)
        return self._build_english_prompt(spanish_text)

    def _build_english_prompt(self, spanish_text):
        prompt = f"""Actúa como un director de doblaje profesional y traductor audiovisual experto en adaptación de guiones (Script Adaptation & Dubbing Localization).
A continuación tienes la transcripción en español de un video para ser doblado al inglés mediante clonación de voz por IA (TTS).

📏 REGLA CRÍTICA DE SEGMENTACIÓN (RANGO OBLIGATORIO: 30 A 60 PALABRAS, MÁXIMO 70-80):
- RANGO IDEAL OBLIGATORIO: Cada segmento DEBE contener entre 30 y 60 palabras (máximo 70 palabras). Esto equivale a 1 o 2 oraciones breves (unos 10 a 18 segundos de locución).
- TOPE MÁXIMO ESTRICTO: NINGÚN segmento debe superar las 70-80 palabras bajo ninguna circunstancia. Si el orador expone una idea larga o habla de corrido, DEBES dividirla obligatoriamente en múltiples fragmentos pequeños.
- ¿POR QUÉ ES OBLIGATORIO?: Los segmentos largos (>70 palabras) causan silencios muertos gigantes al final del segmento, porque el inglés y el motor de IA hablan a un ritmo más compacto y continuo que el español pausado del video original.
- PUNTOS DE CORTE NATURALES: Corta en puntos y seguido, comas de transición, pausas de respiración o conectores lógicos (ej. "por lo tanto", "ahora bien", "por ejemplo", "en este caso"). Cada segmento debe coincidir con una sola acción o concepto en pantalla.

🎯 REGLA DE ORO: BALANCE Y CONTEO ESTRICTO DE PALABRAS (RANGO OBLIGATORIO: 90% A 110%)
En el doblaje por IA, la duración del audio sintetizado depende directamente de la cantidad de palabras:
- Si la adaptación tiene MENOS DEL 90% de palabras: El audio en inglés termina demasiado rápido, dejando vacíos incómodos de silencio en el video y perdiendo información valiosa.
- Si la adaptación tiene MÁS DEL 110% de palabras: El audio se ve obligado a acelerarse de manera artificial y excesiva, arruinando la dicción y la naturalidad del locutor.
- RANGO VÁLIDO Y OBLIGATORIO: La traducción en inglés DEBE tener entre el 90% y el 110% del número de palabras de la frase original en español de ese segmento. El sistema marcará como error cualquier segmento que quede por debajo del 90%.

📐 PROCEDIMIENTO OBLIGATORIO DE CONTEO Y CÁLCULO PARA CADA SEGMENTO:
Antes de redactar la versión final de cada fragmento, DEBES seguir este proceso:
1. Divide el texto fuente en fragmentos pequeños (idealmente entre 30 y 60 palabras, nunca más de 70-80 palabras).
2. Cuenta las palabras exactas de la frase en español del segmento (ejemplo: 45 palabras).
3. Calcula tu rango objetivo de palabras en inglés: mínimo 90% (41 palabras) y máximo 110% (49 palabras).
4. Redacta la adaptación en inglés y cuenta cuántas palabras obtuviste:
   - Si tu traducción en inglés quedó por debajo del 90% (< 41 palabras): ¡NO LA ENTREGUES ASÍ! Es demasiado corta. Amplía la redacción explicando con mayor detalle, utilizando vocabulario técnico preciso, oraciones completas y descripciones ricas sin perder el sentido.
   - Si tu traducción superó el 110% (> 49 palabras): Condensa levemente oraciones secundarias sin omitir datos esenciales.

⚠️ OTRAS REGLAS OBLIGATORIAS:
1. **NO RESUMAS NI OMITAS INFORMACIÓN:** No es un resumen. Debes traducir TODOS los conceptos, detalles, pasos técnicos, advertencias y matices expresados en el original.
2. **NO INFLES CON RELLENO ARTIFICIAL:** No uses muletillas vacías repetitivas. Usa inglés fluido, natural y descriptivo propio de un locutor nativo experto en la materia.
3. **Puntuación y Ritmo:** Cada fragmento debe terminar con puntuación adecuada (punto, interrogación, etc.) para que el generador de voz entone con naturalidad.
4. **Tono Emocional:** Asigna a cada fragmento uno de estos 4 tonos exactos según el contexto:
   - "Conversational": Tono casual, neutro, informal o introductorio.
   - "Explanatory": Tono didáctico, explicando conceptos técnicos o pasos con calma.
   - "Effusive": Tono enérgico, de advertencia, sorpresa, entusiasmo o énfasis marcado.
   - "Serious": Tono formal, conclusión analítica o advertencia de riesgo.

Devuelve ÚNICAMENTE un bloque de código JSON válido con esta estructura exacta (sin texto introductorio, ni despedidas, ni explicaciones adicionales):

[
  {{
    "id": "seg-0",
    "original": "<frase en español (entre 30 y 60 palabras, máx 70-80)>",
    "translated": "<adaptación en inglés verificando que tenga entre el 90% y el 110% de palabras>",
    "tone": "Conversational",
    "filename": "segment_000.wav"
  }},
  {{
    "id": "seg-1",
    "original": "<frase en español (entre 30 y 60 palabras, máx 70-80)>",
    "translated": "<adaptación en inglés verificando que tenga entre el 90% y el 110% de palabras>",
    "tone": "Explanatory",
    "filename": "segment_001.wav"
  }}
]

--- GUION ORIGINAL EN ESPAÑOL ---
{spanish_text}
"""
        return prompt

    def _build_portuguese_prompt(self, spanish_text):
        prompt = f"""Actúa como un director de doblaje profesional y traductor audiovisual experto en adaptación de guiones (Script Adaptation & Dubbing Localization).
A continuación tienes la transcripción en español de un video para ser doblado al PORTUGUÉS DE BRASIL (pt-BR) neutro mediante clonación de voz por IA (TTS) para un canal de trading e inversiones.

📏 REGLA CRÍTICA DE SEGMENTACIÓN (RANGO OBLIGATORIO: 30 A 60 PALABRAS, MÁXIMO 70-80):
- RANGO IDEAL OBLIGATORIO: Cada segmento DEBE contener entre 30 y 60 palabras (máximo 70 palabras). Esto equivale a 1 o 2 oraciones breves (unos 10 a 18 segundos de locución).
- TOPE MÁXIMO ESTRICTO: NINGÚN segmento debe superar las 70-80 palabras bajo ninguna circunstancia. Si el orador expone una idea larga o habla de corrido, DEBES dividirla obligatoriamente en múltiples fragmentos pequeños.
- ¿POR QUÉ ES OBLIGATORIO?: Los segmentos largos (>70 palabras) causan silencios muertos gigantes al final del segmento, porque el audio sintetizado en portugués avanza de forma continua mientras que el español original tiene pausas y silencios naturales.
- PUNTOS DE CORTE NATURALES: Corta en puntos y seguido, comas de transición, pausas de respiración o conectores lógicos (ej. "por lo tanto", "ahora bien", "por ejemplo" / "por exemplo", "então", "além disso"). Cada segmento debe coincidir con una sola acción o concepto en pantalla.

🎯 REGLA DE ORO: BALANCE Y CONTEO ESTRICTO DE PALABRAS (RANGO OBLIGATORIO: 90% A 110%)
En el doblaje por IA, la duración del audio sintetizado depende directamente de la cantidad de palabras:
- Si la adaptación tiene MENOS DEL 90% de palabras: El audio en portugués termina demasiado rápido, dejando vacíos incómodos de silencio en el video y perdiendo información valiosa.
- Si la adaptación tiene MÁS DEL 110% de palabras: El audio se ve obligado a acelerarse de manera artificial y excesiva, arruinando la dicción y la naturalidad del locutor.
- RANGO VÁLIDO Y OBLIGATORIO: La traducción en portugués DEBE tener entre el 90% y el 110% del número de palabras de la frase original en español de ese segmento. El sistema marcará como error cualquier segmento que quede por debajo del 90%.

📐 PROCEDIMIENTO OBLIGATORIO DE CONTEO Y CÁLCULO PARA CADA SEGMENTO:
Antes de redactar la versión final de cada fragmento, DEBES seguir este proceso:
1. Divide el texto fuente en fragmentos pequeños (idealmente entre 30 y 60 palabras, nunca más de 70-80 palabras).
2. Cuenta las palabras exactas de la frase en español del segmento (ejemplo: 45 palabras).
3. Calcula tu rango objetivo de palabras en portugués: mínimo 90% (41 palabras) y máximo 110% (49 palabras).
4. Redacta la adaptación en portugués brasileño natural y cuenta cuántas palabras obtuviste:
   - Si tu traducción en portugués quedó por debajo del 90% (< 41 palabras): ¡NO LA ENTREGUES ASÍ! Es demasiado corta. Amplía la redacción explicando con mayor detalle, utilizando vocabulario técnico preciso, oraciones completas y descripciones ricas sin perder el sentido original.
   - Si tu traducción superó el 110% (> 49 palabras): Condensa levemente oraciones secundarias sin omitir datos esenciales.

⚠️ OTRAS REGLAS OBLIGATORIAS:
1. **NO RESUMAS NI OMITAS INFORMACIÓN:** No es un resumen. Debes traducir TODOS los conceptos, detalles, pasos técnicos, advertencias y matices expresados en el original.
2. **PORTUGUÉS DE BRASIL FLUIDO Y TÉCNICO:** Usa la terminología estándar del mercado financiero y trading en Brasil (ejemplos: *médias móveis, suporte e resistência, rompimento, pullbacks, footprint, fluxo de ordens, robôs traders, stop loss, gerenciamento de risco*).
3. **Puntuación y Ritmo:** Cada fragmento debe terminar con puntuación adecuada (punto, interrogación, etc.) para que el generador de voz entone con naturalidad.
4. **Tono Emocional:** Asigna a cada fragmento uno de estos 4 tonos exactos según el contexto:
   - "Conversational": Tono casual, neutro, informal o introductorio.
   - "Explanatory": Tono didáctico, explicando conceptos técnicos o pasos con calma.
   - "Effusive": Tono enérgico, de advertencia, sorpresa, entusiasmo o énfasis marcado.
   - "Serious": Tono formal, conclusión analítica o advertencia de riesgo.

Devuelve ÚNICAMENTE un bloque de código JSON válido con esta estructura exacta (sin texto introductorio, ni despedidas, ni explicaciones adicionales):

[
  {{
    "id": "seg-0",
    "original": "<frase en español (entre 30 y 60 palabras, máx 70-80)>",
    "translated": "<adaptación en portugués verificando que tenga entre el 90% y el 110% de palabras>",
    "tone": "Conversational",
    "filename": "segment_000.wav"
  }},
  {{
    "id": "seg-1",
    "original": "<frase en español (entre 30 y 60 palabras, máx 70-80)>",
    "translated": "<adaptación en portugués verificando que tenga entre el 90% y el 110% de palabras>",
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
        Utiliza un motor de alineación global en 3 capas (Global Token Matching con SequenceMatcher,
        refinamiento de frontera Head-Tail y guardas de tasa de locución y monotonicidad)
        para ser 100% inmune a falsos positivos por repetición de frases o muletillas idénticas.
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
                    clean_word = normalize_token(word.word)
                    if clean_word:
                        whisper_words.append({
                            "word": clean_word,
                            "start_ms": int(word.start * 1000),
                            "end_ms": int(word.end * 1000)
                        })

            total_whisper_words = len(whisper_words)
            whisper_tokens = [w["word"] for w in whisper_words]

            if callback_status:
                callback_status("Alineando texto semántico global con el audio (Capa 1/3)...")

            # Preparar tokens de Gemini y mapeo de posición de segmentos
            all_gemini_tokens = []
            gemini_segments_info = []

            for seg_idx, item in enumerate(gemini_data):
                raw_words = item.get("original", "").split()
                tokens = [normalize_token(w) for w in raw_words if normalize_token(w)]
                g_start = len(all_gemini_tokens)
                all_gemini_tokens.extend(tokens)
                g_end = len(all_gemini_tokens)
                gemini_segments_info.append({
                    "seg_idx": seg_idx,
                    "tokens": tokens,
                    "g_start": g_start,
                    "g_end": g_end,
                    "count": len(tokens)
                })

            # CAPA 1: Alineador Global Macro (Ratcliff-Obershelp / SequenceMatcher)
            matcher = SequenceMatcher(None, all_gemini_tokens, whisper_tokens, autojunk=False)
            matching_blocks = matcher.get_matching_blocks()

            gemini_to_whisper = {}
            for block in matching_blocks:
                for offset in range(block.size):
                    gemini_to_whisper[block.a + offset] = block.b + offset

            if callback_status:
                callback_status("Optimizando fronteras y aplicando guardas de locución (Capas 2 y 3)...")

            # CAPA 2 & 3: Estimación de frontera, guardas físicas de locución y monotonicidad
            last_confirmed_w_idx = 0

            for seg_info in gemini_segments_info:
                seg_idx = seg_info["seg_idx"]
                tokens = seg_info["tokens"]
                g_start = seg_info["g_start"]
                g_end = seg_info["g_end"]
                count = seg_info["count"]

                # Regla de oro 1: El primer segmento siempre arranca en el tiempo 0 ms
                if seg_idx == 0:
                    best_start_idx = 0
                    start_ms = 0
                else:
                    prev_info = gemini_segments_info[seg_idx - 1]
                    prev_count = prev_info["count"]
                    # Guarda física: el segmento previo no puede haber durado menos del 50% de sus palabras
                    min_physical_word_advance = max(1, int(prev_count * 0.50))
                    min_allowed_w_idx = min(last_confirmed_w_idx + min_physical_word_advance, max(0, total_whisper_words - 1))

                    # 1. Buscar en la cabeza del segmento actual (los primeros tokens)
                    candidate_indices = []
                    for offset in range(min(8, count)):
                        g_pos = g_start + offset
                        if g_pos in gemini_to_whisper:
                            cand_w = gemini_to_whisper[g_pos] - offset
                            if cand_w >= min_allowed_w_idx:
                                candidate_indices.append(cand_w)

                    if candidate_indices:
                        best_start_idx = candidate_indices[0]
                    else:
                        # 2. Buscar en la cola del segmento previo (últimas palabras)
                        prev_tail_candidates = []
                        for offset in range(min(6, prev_count)):
                            g_pos = prev_info["g_end"] - 1 - offset
                            if g_pos in gemini_to_whisper:
                                cand_w = gemini_to_whisper[g_pos] + 1 + offset
                                if cand_w >= min_allowed_w_idx:
                                    prev_tail_candidates.append(cand_w)

                        if prev_tail_candidates:
                            best_start_idx = prev_tail_candidates[0]
                        else:
                            # 3. Fallback: correlación local a partir de la frontera física válida
                            target_slice = tokens[:min(4, count)]
                            search_limit = min(min_allowed_w_idx + 80, total_whisper_words - len(target_slice) + 1)
                            local_best = -1
                            local_best_score = 0
                            for k in range(min_allowed_w_idx, max(min_allowed_w_idx + 1, search_limit)):
                                score = sum(1 for w_off, gw in enumerate(target_slice) if whisper_tokens[k + w_off] == gw)
                                if score > local_best_score:
                                    local_best_score = score
                                    local_best = k
                                    if score == len(target_slice):
                                        break
                            if local_best != -1 and local_best_score >= 2:
                                best_start_idx = local_best
                            else:
                                best_start_idx = min(last_confirmed_w_idx + max(1, prev_count), max(0, total_whisper_words - 1))

                    best_start_idx = max(0, min(best_start_idx, max(0, total_whisper_words - 1)))
                    start_ms = whisper_words[best_start_idx]["start_ms"] if total_whisper_words > 0 else 0

                    # Regla de oro 2: Garantía monótona estricta (ningún segmento intermedio puede ser menor o igual al anterior)
                    prev_start = gemini_data[seg_idx - 1].get("start_ms", 0)
                    if start_ms <= prev_start:
                        start_ms = prev_start + 150

                gemini_data[seg_idx]["start_ms"] = start_ms
                gemini_data[seg_idx]["orig_start_ms"] = start_ms
                last_confirmed_w_idx = best_start_idx

            # Asignar end_ms basándose en el inicio del siguiente segmento (sin solapamientos)
            for i in range(len(gemini_data)):
                if i < len(gemini_data) - 1:
                    next_start = gemini_data[i + 1].get("start_ms")
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
