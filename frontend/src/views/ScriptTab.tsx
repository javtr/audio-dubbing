import React, { useState, useEffect } from 'react';
import { useProjectStore } from '../stores/useProjectStore';
import * as api from '../api/client';
import { Mic, Copy, Save, Timer, Scissors, CheckCircle, AlertTriangle, AlertCircle } from 'lucide-react';

export const ScriptTab: React.FC = () => {
  const {
    currentProject,
    segments,
    validation,
    liveStatusMessage,
    saveCurrentMetadata,
  } = useProjectStore();

  const [transcript, setTranscript] = useState('');
  const [jsonText, setJsonText] = useState('');
  const [splitOnPauses, setSplitOnPauses] = useState(true);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAligning, setIsAligning] = useState(false);
  const [bannerNotice, setBannerNotice] = useState<string | null>(null);

  // Sync JSON text when segments in store change
  useEffect(() => {
    if (segments && segments.length > 0) {
      setJsonText(JSON.stringify(segments, null, 2));
    }
  }, [segments]);

  const handleTranscribe = async () => {
    if (!currentProject) return;
    setIsTranscribing(true);
    try {
      await api.transcribeAudio(currentProject);
    } catch (err: any) {
      alert(`Error al iniciar transcripción: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleCopyPrompt = async () => {
    if (!currentProject) return;
    if (!transcript.trim()) {
      alert('Primero transcribe el audio o pega el texto en el cuadro izquierdo.');
      return;
    }
    try {
      const res = await api.generateGeminiPrompt(currentProject, transcript);
      await navigator.clipboard.writeText(res.prompt);
      setBannerNotice('¡Prompt copiado al portapapeles! Pégalo en Gemini Web y copia el JSON resultante.');
      setTimeout(() => setBannerNotice(null), 6000);
    } catch (err: any) {
      alert(`Error al generar prompt: ${err.message}`);
    }
  };

  const handleSaveJson = async () => {
    if (!currentProject) return;
    try {
      const parsed = JSON.parse(jsonText);
      if (!Array.isArray(parsed)) throw new Error('El JSON debe ser una lista de segmentos [ ... ]');
      useProjectStore.getState().setSegments(parsed);
      await saveCurrentMetadata();
      setBannerNotice(`¡Guardados ${parsed.length} segmentos en el proyecto!`);
      setTimeout(() => setBannerNotice(null), 4000);
    } catch (err: any) {
      alert(`Error en formato JSON: ${err.message}`);
    }
  };

  const handleAlign = async () => {
    if (!currentProject) return;
    try {
      const parsed = JSON.parse(jsonText);
      if (!Array.isArray(parsed) || parsed.length === 0) {
        alert('Pega primero el JSON generado por Gemini en la caja de texto.');
        return;
      }
      setIsAligning(true);
      await api.alignScript(currentProject, parsed, splitOnPauses);
    } catch (err: any) {
      alert(`JSON inválido: ${err.message}`);
    } finally {
      setIsAligning(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      {/* Banner Notice / Live Status */}
      {(bannerNotice || liveStatusMessage) && (
        <div className="bg-sky-500/10 border border-sky-500/30 text-sky-400 px-4 py-2.5 rounded-xl text-xs font-medium flex items-center gap-2">
          <CheckCircle className="w-4 h-4 shrink-0" />
          <span>{bannerNotice || liveStatusMessage}</span>
        </div>
      )}

      {/* Validation Health Banner */}
      {validation && (
        <div
          className={`px-4 py-3 rounded-xl border flex items-center justify-between text-xs font-medium ${
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left Column: Whisper Transcribe */}
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex flex-col h-[calc(100vh-210px)]">
          <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <span>Paso 1A: Transcripción del Audio</span>
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={handleTranscribe}
                disabled={isTranscribing}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <Mic className="w-3.5 h-3.5" />
                <span>{isTranscribing ? 'Transcribiendo...' : 'Transcribir Audio'}</span>
              </button>
              <button
                onClick={handleCopyPrompt}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5"
              >
                <Copy className="w-3.5 h-3.5" />
                <span>Copiar Prompt</span>
              </button>
            </div>
          </div>

          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder="La transcripción de Whisper aparecerá aquí..."
            className="flex-1 w-full bg-neutral-950 border border-neutral-800 rounded-lg p-3 mt-3 text-xs font-mono text-neutral-300 outline-none resize-none focus:border-sky-500"
          />
        </div>

        {/* Right Column: Gemini JSON & Whisper Alignment */}
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex flex-col h-[calc(100vh-210px)]">
          <div className="flex items-center justify-between pb-3 border-b border-neutral-800 flex-wrap gap-2">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <span>Paso 1B: JSON de Gemini y Tiempos</span>
            </h2>

            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-xs text-sky-400 font-semibold cursor-pointer select-none bg-sky-500/10 border border-sky-500/30 px-2 py-1 rounded-lg">
                <input
                  type="checkbox"
                  checked={splitOnPauses}
                  onChange={(e) => setSplitOnPauses(e.target.checked)}
                  className="rounded text-sky-500 focus:ring-0 cursor-pointer"
                />
                <Scissors className="w-3 h-3" />
                <span>Auto-dividir pausas (≥ 1.0s)</span>
              </label>

              <button
                onClick={handleSaveJson}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-neutral-800 hover:bg-neutral-700 text-neutral-200 transition flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Guardar</span>
              </button>

              <button
                onClick={handleAlign}
                disabled={isAligning}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <Timer className="w-3.5 h-3.5" />
                <span>{isAligning ? 'Sincronizando...' : 'Sincronizar Tiempos'}</span>
              </button>
            </div>
          </div>

          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            placeholder="Pega aquí el JSON devuelto por Gemini..."
            className="flex-1 w-full bg-neutral-950 border border-neutral-800 rounded-lg p-3 mt-3 text-xs font-mono text-emerald-400 outline-none resize-none focus:border-sky-500"
          />
        </div>
      </div>
    </div>
  );
};

