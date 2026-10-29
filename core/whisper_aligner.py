import copy
import json
import gc
import math
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

    def transcribe_and_segment_acoustic(self, audio_path, min_silence_s=1.5, callback_status=None):
        """
        Transcribe el audio y lo subdivide directamente en segmentos acústicos
        basándose en los silencios reales entre palabras detectados por Whisper.
        """
        if callback_status:
            callback_status("Iniciando análisis acústico y detección de silencios con Whisper...")
        
        try:
            model = self._get_model()
            segments, info = model.transcribe(audio_path, language="es", beam_size=5, word_timestamps=True)
            audio_duration_ms = int(info.duration * 1000)
            
            all_words = []
            for seg in segments:
                if not hasattr(seg, "words") or not seg.words:
                    continue
                for w in seg.words:
                    w_str = w.word.strip()
                    if w_str:
                        all_words.append({
                            "word": w_str,
                            "start_ms": int(w.start * 1000),
                            "end_ms": int(w.end * 1000)
                        })
                        
            if not all_words:
                return [], "", audio_duration_ms

            min_silence_ms = int(float(min_silence_s) * 1000)
            result_segments = []
            current_words = []
            seg_counter = 1
            formatted_lines = []

            for i in range(len(all_words)):
                cur_w = all_words[i]
                current_words.append(cur_w)
                
                is_last_word = (i == len(all_words) - 1)
                should_split = False
                
                if is_last_word:
                    should_split = True
                else:
                    next_w = all_words[i + 1]
                    gap_ms = next_w["start_ms"] - cur_w["end_ms"]
                    
                    # 1. Silencio acústico real >= min_silence_ms (ej. 1500ms)
                    if gap_ms >= min_silence_ms:
                        should_split = True
                    # 2. Fin de oración (. ? !) + pausa moderada >= 500ms
                    elif cur_w["word"].endswith(('.', '?', '!', '...')) and gap_ms >= 500:
                        should_split = True
                    # 3. Límite de seguridad para evitar frases excesivamente largas
                    elif len(current_words) >= 45 or (cur_w["end_ms"] - current_words[0]["start_ms"]) >= 18000:
                        if cur_w["word"].endswith((',', ';', ':', '.')) or gap_ms >= 250:
                            should_split = True

                if should_split and current_words:
                    start_ms = current_words[0]["start_ms"]
                    # Pequeño respiro acústico de 150ms al final para no cortar consonantes
                    end_ms = current_words[-1]["end_ms"] + 150
                    if not is_last_word:
                        end_ms = min(end_ms, all_words[i + 1]["start_ms"])
                        
                    sentence_text = " ".join(w["word"] for w in current_words).strip()
                    
                    seg_id = seg_counter
                    seg_dict = {
                        "id": seg_id,
                        "original": sentence_text,
                        "translated": "",
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "orig_start_ms": start_ms,
                        "orig_end_ms": end_ms,
                        "filename": f"segment_{seg_id - 1:03d}.wav",
                        "speed_ratio": 1.0,
                        "current_speed_ratio": 1.0,
                        "tone": "Conversational"
                    }
                    result_segments.append(seg_dict)
                    
                    # Formato legible: [00:03 - 00:08] #1: Texto...
                    s_sec = start_ms / 1000.0
                    e_sec = end_ms / 1000.0
                    time_header = f"[{int(s_sec // 60):02d}:{int(s_sec % 60):02d}.{int((s_sec % 1) * 10):d} - {int(e_sec // 60):02d}:{int(e_sec % 60):02d}.{int((e_sec % 1) * 10):d}]"
                    formatted_lines.append(f"{time_header} #{seg_id}: {sentence_text}")
                    
                    seg_counter += 1
                    current_words = []

            formatted_transcript = "\n".join(formatted_lines)
            return result_segments, formatted_transcript, audio_duration_ms
        finally:
            self.unload_model()

    def generate_translation_prompt(self, segments_data, target_lang="en"):
        """
        Genera el prompt listo para Gemini Web con las frases ya delimitadas acústicamente por Whisper.
        Incluye conteo exacto de palabras en español (mínimo) y límite máximo del 120% (palabras_max)
        para garantizar sincronización de doblaje sin sobrecargar los tiempos acústicos,
        y asigna la clasificación de los 4 tonos requeridos (Conversacional, Explicatorio, Efusivo, Serio).
        """
        is_pt = str(target_lang).lower() in ("pt", "portuguese")
        lang_name = "PORTUGUÉS DE BRASIL (pt-BR)" if is_pt else "INGLÉS (English)"

        input_list = []
        for s in segments_data:
            orig = s.get("original", "").strip()
            word_count = len(orig.split()) if orig else 0
            max_words = math.ceil(word_count * 1.20) if word_count > 0 else 0
            input_list.append({
                "id": s.get("id"),
                "original": orig,
                "palabras_es": word_count,
                "palabras_max": max_words
            })

        input_json_str = json.dumps(input_list, indent=2, ensure_ascii=False)

        prompt = f"""Actúa como un director de doblaje y traductor audiovisual profesional de ESPAÑOL a {lang_name}.

A continuación tienes una lista de frases numeradas que fueron extraídas de un audio real con tiempos acústicos fijos.
Tu objetivo es traducir cada frase al {lang_name} y asignar la emoción adecuada respetando estrictamente estas 4 reglas obligatorias:

🎯 INSTRUCCIONES ESTRICTAS:
1. TRADUCCIÓN EXACTA 1-A-1: Traduce exactamente cada frase respetando su mismo "id". NO unas frases ni crees nuevos fragmentos.
2. LONGITUD Y LÍMITE ESTRICTO DE PALABRAS (CRÍTICO PARA DOBLAJE):
   - RANGO PERMITIDO: El número de palabras traducidas en {lang_name} DEBE ubicarse obligatoriamente entre "palabras_es" (100%) y "palabras_max" (máximo 120%).
   - NUNCA MENOS QUE EL MÍNIMO: El conteo en {lang_name} NUNCA debe ser menor que el número de palabras en español indicado en "palabras_es" (conteo {lang_name} >= palabras_es).
   - TOPE MÁXIMO ESTRICTO (120%): El conteo en {lang_name} NUNCA debe superar el valor indicado en "palabras_max" (conteo {lang_name} <= palabras_max).
   - Si la traducción literal resulta más corta que "palabras_es", amplía naturalmente la expresión con vocabulario fluido y conectores conversacionales hasta alcanzar el mínimo sin pasarte jamás de "palabras_max".
   - 🚫 PROHIBIDO EL RELLENO O FRASES INFLADAS: NO inventes conceptos, ni añadas introducciones largas, muletillas vacías o explicaciones redundantes. La traducción debe ser concisa, fluida y respetar estrictamente el rango [palabras_es - palabras_max].
3. CLASIFICACIÓN DE TONO EMOCIONAL (CAMPO "tone"):
   Para cada frase, asigna obligatoriamente uno de estos 4 valores exactos en el campo "tone" según su contenido y contexto:
   - "Conversacional": Saludos, introducciones, tono casual, anécdotas o transiciones fluidas.
   - "Explicatorio": Conceptos pedagógicos, definiciones técnicas, análisis paso a paso o enseñanza.
   - "Efusivo": Momentos de entusiasmo, energía alta, alertas destacadas, llamadas a la acción o sorpresas.
   - "Serio": Advertencias de gestión de riesgo financiero, cláusulas de responsabilidad o conclusiones críticas.
4. FORMATO DE SALIDA ESTRICTO:
   Devuelve ÚNICAMENTE un bloque de código JSON válido con la siguiente estructura (sin textos antes ni después):

[
  {{
    "id": 1,
    "translated": "Traducción natural al {lang_name} respetando estrictamente el rango entre palabras_es y palabras_max...",
    "tone": "Conversacional"
  }}
]

DATOS A TRADUCIR:
```json
{input_json_str}
```"""
        return prompt

    def generate_gemini_prompt(self, spanish_text, target_lang="en"):
        """Genera el prompt listo para copiar y pegar en Gemini Web según el idioma destino ('en' o 'pt')."""
        if str(target_lang).lower() in ("pt", "portuguese"):
            return self._build_portuguese_prompt(spanish_text)
        return self._build_english_prompt(spanish_text)


    def generate_retranslation_prompt(self, segments_data, target_lang="en"):
        """
        Genera un prompt con los segmentos ya divididos acústicamente para que Gemini
        vuelva a traducir el texto en español sin inventar frases ni inflar palabras,
        acotando el conteo de palabras a máximo el 120% de las palabras en español.
        """
        is_pt = str(target_lang).lower() in ("pt", "portuguese")
        lang_name = "PORTUGUÉS DE BRASIL (pt-BR)" if is_pt else "INGLÉS (English)"
        lang_code = "pt" if is_pt else "en"

        input_list = []
        for s in segments_data:
            orig = s.get("original", "").strip()
            words_es = len(orig.split()) if orig else 0
            max_words = math.ceil(words_es * 1.20) if words_es > 0 else 0
            input_list.append({
                "id": s.get("id"),
                "original": orig,
                "palabras_es": words_es,
                "palabras_max": max_words,
                "filename": s.get("filename", "")
            })

        input_json_str = json.dumps(input_list, indent=2, ensure_ascii=False)

        prompt = f"""Actúa como un director de doblaje profesional y traductor audiovisual experto.
A continuación tienes una lista de fragmentos de video en español que YA HAN SIDO DIVIDIDOS y sincronizados acústicamente en la línea de tiempo.

🎯 TU MISIÓN:
Traducir cada uno de los textos en español al {lang_name} para ser doblado por IA (TTS).

📏 REGLA CRÍTICA DE CONTEO Y FIDELIDAD (MÁXIMO 120% DE PALABRAS):
1. **RANGO ESTRICTO DE PALABRAS (100% A 120%):**
   - La traducción en {lang_name} DEBE tener un conteo de palabras entre "palabras_es" (mínimo) y "palabras_max" (máximo 120%).
   - Obligatorio: palabras_es <= conteo_{lang_code} <= palabras_max. NUNCA superes "palabras_max".
2. **PROHIBIDO INVENTAR FRASES O RELLENO ARTIFICIAL:**
   - NO agregues ideas, frases introductorias ni muletillas que no existan en el original en español (NO añadas muletillas artificiales como "as you can see here", "keep in mind", "remember that", etc., salvo que el original lo exprese).
   - Traduce de forma directa, fiel, profesional y fluida dentro del rango permitido.
3. **MANTENER LA ESTRUCTURA EXACTA:**
   - NO unas ni dividas los segmentos. Cada "id" debe devolver exactamente una traducción para su "original".
   - Conserva los mismos "id" y "filename".
   - Asigna un "tone" ("Conversational", "Explanatory", "Effusive", "Serious").

Devuelve ÚNICAMENTE un bloque JSON válido con esta estructura exacta (sin texto introductorio, ni comentarios, ni explicaciones adicionales):

[
  {{
    "id": "seg_000",
    "original": "...",
    "translated": "<traducción en {lang_name} con conteo entre palabras_es y palabras_max sin relleno>",
    "tone": "Conversational",
    "filename": "segment_000.wav"
  }}
]

--- FRAGMENTOS A TRADUCIR EN ESPAÑOL ---
{input_json_str}
"""
        return prompt

    def _build_english_prompt(self, spanish_text):
        prompt = f"""Actúa como un director de doblaje profesional y traductor audiovisual experto en adaptación de guiones (Script Adaptation & Dubbing Localization).
A continuación tienes la transcripción en español de un video para ser doblado al inglés mediante clonación de voz por IA (TTS).

📏 REGLA CRÍTICA DE SEGMENTACIÓN (RANGO OBLIGATORIO: 30 A 60 PALABRAS, MÁXIMO 70-80):
- RANGO IDEAL OBLIGATORIO: Cada segmento DEBE contener entre 30 y 60 palabras en español (máximo 70 palabras). Esto equivale a 1 o 2 oraciones breves (unos 10 a 18 segundos de locución).
- TOPE MÁXIMO ESTRICTO: NINGÚN segmento en español debe superar las 70-80 palabras bajo ninguna circunstancia. Si el orador expone una idea larga o habla de corrido, DEBES dividirla obligatoriamente en múltiples fragmentos pequeños.
- ¿POR QUÉ ES OBLIGATORIO?: Los segmentos largos causan desajustes temporales acumulativos. Fragmentos breves garantizan una sincronización labial y de video perfecta.
- PUNTOS DE CORTE NATURALES: Corta en puntos y seguido, comas de transición, pausas de respiración o conectores lógicos (ej. "por lo tanto", "ahora bien", "por ejemplo", "en este caso"). Cada segmento debe coincidir con una sola acción o concepto en pantalla.

🎯 REGLA DE ORO: EQUIVALENCIA Y CONTEO NATURAL (INGLÉS ≥ ESPAÑOL, RANGO: 100% A 120%)
En el doblaje por IA mediante clonación de voz:
- La adaptación en inglés DEBE igualar o superar levemente el número de palabras en español del segmento (conteo en inglés ≥ conteo en español).
- RANGO PERMITIDO: Entre el 100% y el 120% de las palabras en español (conteo inglés <= 120% palabras español).
- 🚫 PROHIBIDO INVENTAR FRASES O RELLENO ARTIFICIAL: NO inventes conceptos, frases introductorias ni muletillas que no existan en el original en español (NO agregues muletillas artificiales como "as you can see right here", "keep in mind that", "make sure to look at" salvo que el orador lo haya dicho expresamente).
- FIDELIDAD Y NATURALIDAD: Traduce con exactitud, tono nativo, vocabulario técnico preciso y oraciones completas y fluidas.

📐 PROCEDIMIENTO DE CONTEO PARA CADA SEGMENTO:
1. Cuenta las palabras de la frase en español del segmento (ejemplo: 40 palabras).
2. Redacta la versión en inglés procurando que tenga al menos el mismo número de palabras o un poco más (ejemplo: 40 a 44 palabras).
3. Si quedó ligeramente por debajo (< 40 palabras), usa oraciones completas con sujeto explícito y terminología técnica exacta sin inventar información inexistente.

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
    "translated": "<traducción en inglés verificando que palabras_inglés >= palabras_español (rango 100%-120%) sin inventar frases inexistentes>",
    "tone": "Conversational",
    "filename": "segment_000.wav"
  }},
  {{
    "id": "seg-1",
    "original": "<frase en español (entre 30 y 60 palabras, máx 70-80)>",
    "translated": "<traducción en inglés verificando que palabras_inglés >= palabras_español (rango 100%-120%) sin inventar frases inexistentes>",
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

    def _split_segment_text(self, seg, ratio):
        orig_text = seg.get("original", "").strip()
        trans_text = seg.get("translated", "").strip()

        # 1. Dividir texto en español (original)
        words_es = orig_text.split()
        target_idx_es = max(3, min(len(words_es) - 4, int(round(len(words_es) * ratio)) - 1))

        best_es = target_idx_es
        for off in range(4):
            for candidate in [target_idx_es + off, target_idx_es - off]:
                if 2 <= candidate < len(words_es) - 3:
                    w = words_es[candidate]
                    if w.endswith((',', ';', ':', '.')):
                        best_es = candidate
                        break
            else:
                continue
            break

        part1_es = " ".join(words_es[:best_es + 1]).strip()
        part2_es = " ".join(words_es[best_es + 1:]).strip()

        # 2. Dividir texto traducido (inglés o portugués)
        words_tr = trans_text.split()
        actual_ratio = len(part1_es.split()) / float(max(1, len(words_es)))
        target_idx_tr = max(3, min(len(words_tr) - 4, int(round(len(words_tr) * actual_ratio)) - 1))

        best_tr = target_idx_tr
        connectors = {"and", "but", "so", "because", "which", "while", "that", "e", "mas", "para", "entonces"}
        for off in range(4):
            for cand in [target_idx_tr + off, target_idx_tr - off]:
                if 2 <= cand < len(words_tr) - 3:
                    w = words_tr[cand]
                    if w.endswith((',', ';', ':', '.')) or (cand + 1 < len(words_tr) and words_tr[cand + 1].lower() in connectors):
                        best_tr = cand
                        break
            else:
                continue
            break

        part1_tr = " ".join(words_tr[:best_tr + 1]).strip()
        part2_tr = " ".join(words_tr[best_tr + 1:]).strip()

        return part1_es, part2_es, part1_tr, part2_tr

    def _split_segment_by_acoustic_pauses(self, seg, start_w_idx, end_w_idx, whisper_words, min_pause_ms=1000):
        sub_words = whisper_words[start_w_idx:end_w_idx]
        if len(sub_words) < 10:
            seg["_sub_words"] = sub_words
            return [seg]

        pauses = []
        for k in range(3, len(sub_words) - 4):
            w_curr = sub_words[k]
            w_next = sub_words[k + 1]
            gap = w_next["start_ms"] - w_curr["end_ms"]
            if gap >= min_pause_ms:
                pauses.append((k, gap, w_curr, w_next))

        if not pauses:
            seg["_sub_words"] = sub_words
            return [seg]

        mid_idx = len(sub_words) // 2
        best_pause = max(pauses, key=lambda p: (p[1] - abs(p[0] - mid_idx) * 20))
        k, gap, w_curr, w_next = best_pause

        ratio = (k + 1) / float(len(sub_words))
        part1_es, part2_es, part1_tr, part2_tr = self._split_segment_text(seg, ratio)

        start_1 = seg["start_ms"]
        end_1 = w_curr["end_ms"] + 150
        start_2 = w_next["start_ms"]
        end_2 = seg.get("end_ms", w_next["start_ms"] + 2000)

        base_id = str(seg.get("id", "seg"))

        seg_a = copy.deepcopy(seg)
        seg_a["id"] = f"{base_id}_a"
        seg_a["original"] = part1_es
        seg_a["translated"] = part1_tr
        seg_a["start_ms"] = start_1
        seg_a["end_ms"] = end_1
        seg_a["_sub_words"] = sub_words[:k + 1]

        seg_b = copy.deepcopy(seg)
        seg_b["id"] = f"{base_id}_b"
        seg_b["original"] = part2_es
        seg_b["translated"] = part2_tr
        seg_b["start_ms"] = start_2
        seg_b["end_ms"] = end_2
        seg_b["_sub_words"] = sub_words[k + 1:]

        return [seg_a, seg_b]

    def align_timestamps(self, audio_path, gemini_data, callback_status=None, split_on_pauses=True, min_pause_ms=1000):
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
                            "raw_word": word.word.strip(),
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
                gemini_data[seg_idx]["_w_idx"] = best_start_idx
                last_confirmed_w_idx = best_start_idx

            # CAPA 4: Subdivisión acústica por pausas internas (si está activado)
            if split_on_pauses and total_whisper_words > 0:
                if callback_status:
                    callback_status("Detectando silencios acústicos y auto-subdividiendo frases...")
                expanded_data = []
                for i in range(len(gemini_data)):
                    seg = gemini_data[i]
                    w_start = seg.get("_w_idx", 0)
                    w_end = gemini_data[i + 1].get("_w_idx", total_whisper_words) if i + 1 < len(gemini_data) else total_whisper_words
                    sub_segs = self._split_segment_by_acoustic_pauses(seg, w_start, w_end, whisper_words, min_pause_ms=min_pause_ms)
                    expanded_data.extend(sub_segs)
                gemini_data = expanded_data

            # CAPA 5: Asignación de end_ms acústico real (evita absorber silencios muertos posteriores)
            for i in range(len(gemini_data)):
                seg_i = gemini_data[i]
                sw = seg_i.get("_sub_words", [])
                if sw:
                    actual_voice_end = sw[-1]["end_ms"]
                else:
                    actual_voice_end = seg_i.get("end_ms", seg_i.get("start_ms", 0) + 1000)

                next_start = gemini_data[i + 1].get("start_ms") if i + 1 < len(gemini_data) else audio_duration_ms
                trailing_silence = next_start - actual_voice_end

                if trailing_silence >= 1200:
                    # El orador terminó de hablar: dejar el silencio libre en la pista en vez de hinchar el slot
                    seg_i["end_ms"] = min(next_start, actual_voice_end + 250)
                else:
                    seg_i["end_ms"] = next_start

                # Asegurar duración mínima de 300ms
                if seg_i["end_ms"] <= seg_i["start_ms"]:
                    seg_i["end_ms"] = seg_i["start_ms"] + 300

                # Guardar anclas de inicio y fin originales
                seg_i["orig_start_ms"] = seg_i["start_ms"]
                seg_i["orig_end_ms"] = seg_i["end_ms"]
                seg_i["filename"] = f"segment_{i:03d}.wav"

                # Limpieza de campos temporales internos
                seg_i.pop("_w_idx", None)
                seg_i.pop("_sub_words", None)

            return gemini_data, audio_duration_ms
        finally:
            self.unload_model()
