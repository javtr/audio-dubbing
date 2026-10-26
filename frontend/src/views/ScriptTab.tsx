import React, { useState, useEffect } from 'react';
import { useProjectStore } from '../stores/useProjectStore';
import * as api from '../api/client';
import {
  Mic,
  Copy,
  Save,
  Scissors,
  CheckCircle,
  AlertTriangle,
  Sparkles,
  Download,
  Clock,
  Layers,
} from 'lucide-react';

export const ScriptTab: React.FC = () => {
  const {
    currentProject,
    segments,
    validation,
    liveStatusMessage,
    saveCurrentMetadata,
    setSegments,
    transcript,
    setTranscript,
  } = useProjectStore();

  const [minSilenceS, setMinSilenceS] = useState<number>(1.5);
  const [jsonText, setJsonText] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isCopyingPrompt, setIsCopyingPrompt] = useState(false);
  const [isApplyingTranslation, setIsApplyingTranslation] = useState(false);
  const [bannerNotice, setBannerNotice] = useState<string | null>(null);

  // Sync JSON text when segments in store change
  useEffect(() => {
    if (segments && segments.length > 0) {
      setJsonText(JSON.stringify(segments, null, 2));
    }
  }, [segments]);

  // Transcribe and segment directly using Whisper's acoustic silence detection
  const handleTranscribeAndSegment = async () => {
    if (!currentProject) {
      alert('Selecciona un proyecto primero.');
      return;
    }
    setIsTranscribing(true);
    try {
      await api.transcribeAndSegment(currentProject, minSilenceS);
      setBannerNotice(
        `Iniciando análisis acústico con pausas ≥ ${minSilenceS}s. Whisper transcribirá y dividirá las frases...`
      );
    } catch (err: any) {
      alert(`Error al iniciar transcripción y segmentación: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsTranscribing(false);
    }
  };

  // Generate and copy translation prompt for Gemini (1-to-1)
  const handleCopyTranslationPrompt = async () => {
    if (!currentProject) return;
    if (!segments || segments.length === 0) {
      alert('Primero debes transcribir y segmentar el audio con el botón "1. Transcribir y Segmentar".');
      return;
    }
    setIsCopyingPrompt(true);
    try {
      const res = await api.generateTranslationPrompt(currentProject);
      await navigator.clipboard.writeText(res.prompt);
      setBannerNotice(
        `¡Prompt de traducción copiado (${res.segments_count} frases)! Pégalo en Gemini Web y luego pega el JSON resultante en la caja derecha.`
      );
      setTimeout(() => setBannerNotice(null), 8000);
    } catch (err: any) {
      alert(`Error al generar prompt de traducción: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsCopyingPrompt(false);
    }
  };

  // Apply Gemini's translated JSON into existing acoustic segments
  const handleApplyTranslation = async () => {
    if (!currentProject) return;
    try {
      const parsed = JSON.parse(jsonText);
      if (!Array.isArray(parsed) || parsed.length === 0) {
        alert('Pega el JSON devuelto por Gemini en la caja de texto derecha.');
        return;
      }
      setIsApplyingTranslation(true);
      const res = await api.applyTranslation(currentProject, parsed);
      setSegments(res.metadata);
      setBannerNotice(
        `¡Traducción aplicada a ${res.updated_count} frases! Todos los tiempos acústicos milimétricos se conservaron intactos.`
      );
      setTimeout(() => setBannerNotice(null), 6000);
    } catch (err: any) {
      alert(`Error al aplicar traducción: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsApplyingTranslation(false);
    }
  };

  const handleSaveJson = async () => {
    if (!currentProject) return;
    try {
      const parsed = JSON.parse(jsonText);
      if (!Array.isArray(parsed)) throw new Error('El JSON debe ser una lista de segmentos [ ... ]');
      setSegments(parsed);
      await saveCurrentMetadata();
      setBannerNotice(`¡Guardados ${parsed.length} segmentos en el proyecto!`);
      setTimeout(() => setBannerNotice(null), 4000);
    } catch (err: any) {
      alert(`Error en formato JSON: ${err.message}`);
    }
  };

  const translatedCount = segments.filter(
    (s) => s.translated && s.translated.trim().length > 0
  ).length;

  return (
    <div className="max-w-7xl w-full mx-auto p-4 flex-1 min-h-0 flex flex-col gap-4">
      {/* Banner Notice / Live Status */}
      {(bannerNotice || liveStatusMessage) && (
        <div className="bg-sky-500/10 border border-sky-500/30 text-sky-400 px-4 py-2.5 rounded-xl text-xs font-medium flex items-center gap-2 shadow-sm shrink-0">
          <CheckCircle className="w-4 h-4 shrink-0 text-sky-400" />
          <span>{bannerNotice || liveStatusMessage}</span>
        </div>
      )}

      {/* Validation Health Banner */}
      {validation && (
        <div
          className={`px-4 py-3 rounded-xl border flex items-center justify-between text-xs font-medium shrink-0 ${
            validation.has_errors
              ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
              : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          }`}
        >
          <div className="flex items-center gap-2">
            {validation.has_errors ? (
              <AlertTriangle className="w-4 h-4 text-rose-400" />
            ) : (
              <CheckCircle className="w-4 h-4 text-emerald-400" />
            )}
            <span>{validation.summary_text}</span>
          </div>
          <span className="text-neutral-400 font-mono">
            {validation.total_count} segmentos analizados
          </span>
        </div>
      )}

      {/* Dual Column Layout */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left Column: Whisper Acoustic Segmentation */}
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex flex-col min-h-0 h-full">
          <div className="flex items-center justify-between pb-3 border-b border-neutral-800 shrink-0 flex-wrap gap-2">
            <div>
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <Scissors className="w-4 h-4 text-sky-400" />
                <span>Paso 1A: Detección Acústica y División (Whisper)</span>
              </h2>
              <p className="text-[11px] text-neutral-400 mt-0.5">
                Whisper escucha el audio original y corta por pausas de silencio reales.
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Silence pause threshold selector */}
              <div className="flex items-center gap-1.5 bg-neutral-950 border border-neutral-800 rounded-lg px-2 py-1 text-xs">
                <Clock className="w-3.5 h-3.5 text-neutral-400" />
                <span className="text-neutral-400">Pausa:</span>
                <select
                  value={minSilenceS}
                  onChange={(e) => setMinSilenceS(parseFloat(e.target.value))}
                  className="bg-transparent text-sky-400 font-semibold outline-none cursor-pointer text-xs"
                >
                  <option value={1.0} className="bg-neutral-900 text-white">
                    1.0s (Pausas cortas)
                  </option>
                  <option value={1.5} className="bg-neutral-900 text-white">
                    1.5s (Recomendado)
                  </option>
                  <option value={2.0} className="bg-neutral-900 text-white">
                    2.0s (Segmentos largos)
                  </option>
                </select>
              </div>

              {/* Action Button: Transcribe & Segment */}
              <button
                onClick={handleTranscribeAndSegment}
                disabled={isTranscribing}
                className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-sky-500 hover:bg-sky-400 text-white transition flex items-center gap-1.5 shadow-sm shadow-sky-500/20 disabled:opacity-50"
                title="Whisper transcribe palabra por palabra y divide el audio donde detecta pausas de silencio reales"
              >
                <Mic className="w-3.5 h-3.5" />
                <span>{isTranscribing ? 'Segmentando...' : '1. Transcribir y Segmentar'}</span>
              </button>
            </div>
          </div>

          {/* Subheader info pill */}
          <div className="py-2 flex items-center justify-between text-xs text-neutral-400 shrink-0">
            <div className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-sky-400" />
              <span>
                {segments.length > 0
                  ? `${segments.length} secciones acústicas detectadas`
                  : 'Sin audio segmentado aún'}
              </span>
            </div>
            <span className="text-[11px] text-neutral-500">
              Marcas de tiempo exactas del audio original
            </span>
          </div>

          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder="Al presionar '1. Transcribir y Segmentar', aquí aparecerán todas las frases numeradas con sus tiempos exactos de inicio y fin..."
            className="flex-1 min-h-0 w-full bg-neutral-950 border border-neutral-800 rounded-lg p-3 text-xs font-mono text-neutral-300 outline-none resize-none focus:border-sky-500 leading-relaxed"
          />
        </div>

        {/* Right Column: Gemini 1-to-1 Linguistic Translation */}
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex flex-col min-h-0 h-full">
          <div className="flex items-center justify-between pb-3 border-b border-neutral-800 flex-wrap gap-2 shrink-0">
            <div>
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-violet-400" />
                <span>Paso 1B: Traducción de Frases (Gemini)</span>
              </h2>
              <p className="text-[11px] text-neutral-400 mt-0.5">
                Gemini traduce frase a frase 1-a-1 sin tocar los tiempos acústicos.
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Button: Copy Translation Prompt */}
              <button
                onClick={handleCopyTranslationPrompt}
                disabled={isCopyingPrompt || segments.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-violet-600 hover:bg-violet-500 text-white transition flex items-center gap-1.5 shadow-sm shadow-violet-600/30 disabled:opacity-40"
                title="Genera y copia el prompt con las frases numeradas para que Gemini las traduzca 1-a-1"
              >
                <Copy className="w-3.5 h-3.5" />
                <span>2. Copiar Prompt Traducción</span>
              </button>

              {/* Button: Apply Translation */}
              <button
                onClick={handleApplyTranslation}
                disabled={isApplyingTranslation || segments.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow-sm shadow-emerald-600/30 disabled:opacity-40"
                title="Aplica la traducción de Gemini a los segmentos conservando al 100% los tiempos acústicos"
              >
                <Download className="w-3.5 h-3.5" />
                <span>3. Aplicar Traducción</span>
              </button>

              <button
                onClick={handleSaveJson}
                className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition flex items-center gap-1"
                title="Guardar JSON manualmente"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Guardar</span>
              </button>
            </div>
          </div>

          {/* Subheader info pill */}
          <div className="py-2 flex items-center justify-between text-xs text-neutral-400 shrink-0">
            <div className="flex items-center gap-1.5">
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                  translatedCount === segments.length && segments.length > 0
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                    : translatedCount > 0
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'bg-neutral-800 text-neutral-400 border border-neutral-700'
                }`}
              >
                {translatedCount === segments.length && segments.length > 0
                  ? `✓ ${translatedCount}/${segments.length} frases traducidas (Completo)`
                  : translatedCount > 0
                  ? `${translatedCount}/${segments.length} frases traducidas`
                  : 'Pendiente de traducir'}
              </span>
            </div>
            <span className="text-[11px] text-neutral-500">
              Pega el JSON de Gemini y pulsa 'Aplicar Traducción'
            </span>
          </div>

          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            placeholder={`Pega aquí el JSON traducido devuelto por Gemini:\n[\n  {\n    "id": 1,\n    "translated": "Hello everyone, welcome."\n  },\n  {\n    "id": 2,\n    "translated": "In this video we will explain..."\n  }\n]`}
            className="flex-1 min-h-0 w-full bg-neutral-950 border border-neutral-800 rounded-lg p-3 text-xs font-mono text-emerald-400 outline-none resize-none focus:border-sky-500 leading-relaxed"
          />
        </div>
      </div>
    </div>
  );
};
