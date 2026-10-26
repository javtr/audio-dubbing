import React, { useState } from 'react';
import { useProjectStore } from '../stores/useProjectStore';
import { SegmentCardItem } from '../components/dubbing/SegmentCardItem';
import * as api from '../api/client';
import { Rocket, StopCircle, RefreshCw, Zap, Search, AlertCircle, CheckCircle } from 'lucide-react';

export const DubbingTab: React.FC = () => {
  const {
    currentProject,
    segments,
    validation,
    references,
    liveStatusMessage,
    liveProgress,
    isBatchGenerating,
  } = useProjectStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [filterMissingOnly, setFilterMissingOnly] = useState(false);
  const [defaultBatchRef, setDefaultBatchRef] = useState('ref_Conversational');

  // Filter segments
  const filteredSegments = segments.filter((seg) => {
    if (filterMissingOnly && seg.clip_duration_ms && seg.clip_duration_ms > 0) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const inId = String(seg.id).toLowerCase().includes(q);
      const inOrig = seg.original.toLowerCase().includes(q);
      const inTrans = seg.translated.toLowerCase().includes(q);
      return inId || inOrig || inTrans;
    }
    return true;
  });

  const handleGenerateAll = async () => {
    if (!currentProject) return;
    const ids = segments.map((s) => s.id);
    try {
      await api.generateBatchTTS(currentProject, ids, defaultBatchRef);
    } catch (err: any) {
      alert(`Error al iniciar lote: ${err.message}`);
    }
  };

  const handleGenerateMissing = async () => {
    if (!currentProject) return;
    const missing = segments.filter((s) => !s.clip_duration_ms || s.clip_duration_ms <= 0).map((s) => s.id);
    if (missing.length === 0) {
      alert('¡Todos los segmentos ya tienen audio generado!');
      return;
    }
    try {
      await api.generateBatchTTS(currentProject, missing, defaultBatchRef);
    } catch (err: any) {
      alert(`Error al iniciar lote: ${err.message}`);
    }
  };

  const handleStop = async () => {
    try {
      await api.stopTTS();
    } catch (err: any) {
      console.error(err);
    }
  };

  return (
    <div className="max-w-7xl w-full mx-auto p-4 flex-1 min-h-0 flex flex-col gap-4">
      {/* Top Action Bar */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={handleGenerateAll}
            disabled={isBatchGenerating}
            className="px-4 py-2 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-2 shadow-lg shadow-emerald-600/20 disabled:opacity-50"
          >
            <Rocket className="w-4 h-4" />
            <span>Solicitar Todos a Pinokio</span>
          </button>

          <button
            onClick={handleGenerateMissing}
            disabled={isBatchGenerating}
            className="px-3.5 py-2 rounded-lg text-xs font-bold bg-sky-600 hover:bg-sky-500 text-white transition flex items-center gap-2 disabled:opacity-50"
          >
            <Zap className="w-4 h-4" />
            <span>Generar Faltantes</span>
          </button>

          <button
            onClick={handleStop}
            disabled={!isBatchGenerating}
            className="px-3.5 py-2 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white transition flex items-center gap-1.5 disabled:opacity-40"
          >
            <StopCircle className="w-4 h-4" />
            <span>Detener</span>
          </button>

          <div className="flex items-center gap-1.5 bg-neutral-950 border border-neutral-800 rounded-lg px-2.5 py-1.5 text-xs">
            <span className="text-neutral-400">Voz Lote:</span>
            <select
              value={defaultBatchRef}
              onChange={(e) => setDefaultBatchRef(e.target.value)}
              className="bg-transparent text-white outline-none cursor-pointer font-semibold"
            >
              {references.map((r) => (
                <option key={r.segmento} value={r.segmento} className="bg-neutral-900 text-neutral-200">
                  {r.tono}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Search & Filter */}
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-neutral-300 font-medium cursor-pointer select-none">
            <input
              type="checkbox"
              checked={filterMissingOnly}
              onChange={(e) => setFilterMissingOnly(e.target.checked)}
              className="rounded text-sky-500 cursor-pointer"
            />
            <span>Solo sin audio</span>
          </label>

          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-neutral-500" />
            <input
              type="text"
              placeholder="Buscar segmento..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-neutral-950 border border-neutral-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-neutral-200 outline-none w-48 focus:border-sky-500"
            />
          </div>
        </div>
      </div>

      {/* Progress Bar (During batch TTS) */}
      {liveProgress && (
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 space-y-2 shrink-0">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-sky-400 flex items-center gap-2">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>{liveStatusMessage}</span>
            </span>
            <span className="text-neutral-400 font-mono">
              {liveProgress.current} / {liveProgress.total} ({liveProgress.percent}%)
            </span>
          </div>
          <div className="w-full bg-neutral-950 h-2.5 rounded-full overflow-hidden border border-neutral-800">
            <div
              className="bg-gradient-to-r from-sky-500 to-emerald-500 h-full transition-all duration-300 rounded-full"
              style={{ width: `${liveProgress.percent}%` }}
            />
          </div>
        </div>
      )}

      {/* Cards Container */}
      <div className="flex-1 min-h-0 overflow-y-auto pr-2 flex flex-col gap-4 rounded-xl pb-2">
        {filteredSegments.length === 0 ? (
          <div className="p-12 text-center text-neutral-500 bg-neutral-900 border border-neutral-800 rounded-xl">
            No se encontraron segmentos para mostrar con los filtros actuales.
          </div>
        ) : (
          filteredSegments.map((seg, idx) => (
            <SegmentCardItem key={seg.id} segment={seg} index={idx} />
          ))
        )}
      </div>
    </div>
  );
};

