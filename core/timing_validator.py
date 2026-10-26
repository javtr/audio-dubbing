import re

class TimingValidator:
    """Motor de validación de consistencia y salud temporal de los segmentos."""

    @staticmethod
    def validate(segments_data, total_duration_ms=None):
        """
        Analiza la lista de segmentos y detecta posibles inconsistencias o errores de alineación:
        - Inicio en 0 ms en segmentos que no son el primero.
        - Desorden cronológico (start_ms < anterior start_ms).
        - Duración congelada o negativa (end_ms <= start_ms).
        - Duración desproporcionada (frases muy breves con duraciones excesivas > 25s o segmentos > 50s).
        - Segmento excesivamente largo (> 150 palabras).
        """
        anomalies = {}
        if not segments_data:
            return {
                "has_errors": False,
                "error_count": 0,
                "total_count": 0,
                "anomalies": {},
                "summary_text": "No hay segmentos cargados."
            }

        prev_start = -1

        for i, seg in enumerate(segments_data):
            seg_id = str(seg.get("id", f"seg-{i}"))
            start_ms = seg.get("start_ms", 0)
            end_ms = seg.get("end_ms", 0)
            orig_text = seg.get("original", "").strip()
            words = [w for w in re.sub(r'[^\w\s]', '', orig_text.lower()).split() if w]
            word_count = len(words)
            dur_ms = end_ms - start_ms

            issues = []

            # 1. Inicio en 0 ms
            if i > 0 and start_ms == 0:
                issues.append("Inicio en 0 ms (posible fallo de sincronización)")

            # 2. Desorden cronológico
            if i > 0 and start_ms < prev_start:
                issues.append(f"Inicia a los {start_ms} ms, antes del segmento anterior ({prev_start} ms)")

            # 3. Duración cero o negativa
            if dur_ms <= 0:
                issues.append(f"Duración nula o negativa ({dur_ms} ms)")

            # 4. Duración desproporcionada
            if word_count < 10 and dur_ms > 25000:
                issues.append(f"Duración excesiva ({dur_ms/1000:.1f}s para solo {word_count} palabras)")
            elif dur_ms > 50000:
                issues.append(f"Duración muy larga ({dur_ms/1000:.1f}s)")

            # 5. Segmento excesivamente largo (> 80 palabras)
            if word_count > 80:
                issues.append(f"Segmento muy largo ({word_count} palabras, recomendado entre 30 y 60, máx 80)")

            # 6. Traslape de audio con el siguiente segmento
            if i < len(segments_data) - 1:
                next_seg = segments_data[i + 1]
                next_start = next_seg.get("start_ms", 0)
                clip_dur = seg.get("clip_duration_ms", 0)
                audio_end = start_ms + (clip_dur if clip_dur > 0 else dur_ms)
                if audio_end > next_start + 20:
                    overlap_ms = audio_end - next_start
                    next_id = str(next_seg.get("id", f"seg-{i+1}"))
                    issues.append(f"Traslape de audio: se monta {overlap_ms}ms sobre el segmento [{next_id}]")

            if issues:
                anomalies[seg_id] = issues

            prev_start = start_ms

        has_errors = len(anomalies) > 0
        error_count = len(anomalies)
        total_count = len(segments_data)

        if not has_errors:
            summary = f"✅ Sincronización íntegra: todos los segmentos ({total_count}/{total_count}) están en orden cronológico."
        else:
            bad_ids = ", ".join(str(k) for k in list(anomalies.keys())[:5])
            if error_count > 5:
                bad_ids += f" y {error_count - 5} más"
            summary = f"⚠️ Se detectaron advertencias en {error_count} segmento(s): [{bad_ids}]. Revisa los tiempos."

        return {
            "has_errors": has_errors,
            "error_count": error_count,
            "total_count": total_count,
            "anomalies": anomalies,
            "summary_text": summary
        }
