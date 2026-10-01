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
            seg_id = seg.get("id", f"seg-{i}")
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

            if issues:
                anomalies[seg_id] = issues

            prev_start = start_ms

        has_errors = len(anomalies) > 0
        error_count = len(anomalies)
        total_count = len(segments_data)

        if not has_errors:
            summary = f"✅ Sincronización íntegra: todos los segmentos ({total_count}/{total_count}) están en orden cronológico."
        else:
            bad_ids = ", ".join(list(anomalies.keys())[:5])
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
