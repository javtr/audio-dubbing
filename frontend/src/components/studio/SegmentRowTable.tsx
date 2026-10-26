import React, { useState, useEffect } from 'react';
import { Segment } from '../../types';
import { useProjectStore } from '../../stores/useProjectStore';
import * as api from '../../api/client';
import { Play, Pause, Save, Trash2, Zap, RotateCcw, Check, RefreshCw, AlertTriangle } from 'lucide-react';
import { detectOverlaps, OverlapAnalysisResult } from '../../utils/overlapDetector';

interface Props {
  onRefreshWaveforms: () => void;
  onOverlapsChange?: (result: OverlapAnalysisResult) => void;
}

export const SegmentRowTable: React.FC<Props> = ({ onRefreshWaveforms, onOverlapsChange }) => {
  const {
    currentProject,
    segments,
    selectedSegmentId,
    setSelectedSegmentId,
    updateSegment,
    saveCurrentMetadata,
    reloadProject,
  } = useProjectStore();

  const [playingSegmentId, setPlayingSegmentId] = useState<string | null>(null);
  const [activeAudio, setActiveAudio] = useState<HTMLAudioElement | null>(null);
  const [adjustingId, setAdjustingId] = useState<string | null>(null);
  const [isApplyingTimings, setIsApplyingTimings] = useState(false);

  // Local state for numeric inputs so typing isn't interrupted
  const [localStarts, setLocalStarts] = useState<Record<string, number>>({});
  const [localRatios, setLocalRatios] = useState<Record<string, number>>({});

  // Resetear estados locales al cambiar de proyecto para evitar estados fantasmas
  useEffect(() => {
    setLocalStarts({});
    setLocalRatios({});
  }, [currentProject]);

  // Sincronizar inputs locales cuando cambian los segmentos
  useEffect(() => {
    setLocalStarts((prev) => {
      const nextStarts = { ...prev };
      segments.forEach((s) => {
        const sid = String(s.id);
        if (nextStarts[sid] === undefined) {
          nextStarts[sid] = s.start_ms;
        }
      });
      return nextStarts;
    });

    setLocalRatios((prev) => {
      const nextRatios = { ...prev };
      segments.forEach((s) => {
        const sid = String(s.id);
        if (nextRatios[sid] === undefined) {
          nextRatios[sid] = s.speed_ratio ?? s.current_speed_ratio ?? 1.0;
        }
      });
      return nextRatios;
    });
  }, [segments]);

  // Análisis dinámico y en tiempo real de traslapes/colisiones entre segmentos
  const overlapAnalysis = detectOverlaps(segments, localStarts, localRatios);

  useEffect(() => {
    onOverlapsChange?.(overlapAnalysis);
  }, [overlapAnalysis, onOverlapsChange]);

  // Reproducir fragmento individual con cache-buster dinámico
  const handleTogglePlay = (seg: Segment) => {
    const segId = String(seg.id);
    if (playingSegmentId === segId && activeAudio) {
      console.log(`[SegmentRowTable] Deteniendo reproducción de ${seg.filename}`);
      activeAudio.pause();
      setActiveAudio(null);
      setPlayingSegmentId(null);
      return;
    }

    if (activeAudio) {
      activeAudio.pause();
    }

    if (!currentProject) return;
    // Parámetro ?t=${Date.now()} para asegurar que el navegador nunca use caché de audio anterior
    const url = `/api/audio/${currentProject}/segment/${seg.filename}?t=${Date.now()}`;
    console.log(`[SegmentRowTable] Reproduciendo fragmento ${seg.filename} (url: ${url})`);
    const audio = new Audio(url);
    audio.onended = () => {
      console.log(`[SegmentRowTable] Fin de reproducción: ${seg.filename}`);
      setPlayingSegmentId(null);
    };
    audio.onerror = (e) => {
      console.error(`[SegmentRowTable] Error reproduciendo ${seg.filename}:`, e);
      setPlayingSegmentId(null);
    };
    audio.play().catch((err) => {
      console.warn(`[SegmentRowTable] Reproducción interrumpida o bloqueada:`, err);
      setPlayingSegmentId(null);
    });

    setActiveAudio(audio);
    setPlayingSegmentId(segId);
  };

  // Ajustar ratio personalizado con FFmpeg atempo (y sincronizar inicio ms si fue editado)
  const handleAdjustRatio = async (seg: Segment) => {
    if (!currentProject) return;
    const segId = String(seg.id);
    const r = localRatios[segId] ?? seg.speed_ratio ?? seg.current_speed_ratio ?? 1.0;
    const startMs = localStarts[segId] ?? seg.start_ms;

    console.log(`[SegmentRowTable] Solicitando ajuste: seg=${segId}, ratio=${r}, start_ms=${startMs}`);
    setAdjustingId(segId);
    try {
      const res = await api.adjustSegmentRatio(currentProject, segId, r, startMs);
      const confirmedRatio = res.segment.speed_ratio ?? res.segment.current_speed_ratio ?? r;
      console.log(`[SegmentRowTable] Servidor confirmó: seg=${segId}, ratio=${confirmedRatio}, dur=${res.segment.clip_duration_ms}ms, fin=${res.segment.end_ms}ms`);
      
      updateSegment(seg.id, {
        start_ms: res.segment.start_ms,
        clip_duration_ms: res.segment.clip_duration_ms,
        speed_ratio: confirmedRatio,
        current_speed_ratio: confirmedRatio,
        is_manual_ratio: true,
        end_ms: res.segment.end_ms,
      });
      setLocalStarts((prev) => ({ ...prev, [segId]: res.segment.start_ms }));
      setLocalRatios((prev) => ({ ...prev, [segId]: confirmedRatio }));
      onRefreshWaveforms();
    } catch (err: any) {
      console.error(`[SegmentRowTable] Error al ajustar velocidad:`, err);
      alert(`Error al ajustar velocidad: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setAdjustingId(null);
    }
  };

  // Restaurar este segmento individual a su audio virgen original de la IA (1.0x)
  const handleResetSegmentAudio = async (seg: Segment) => {
    if (!currentProject) return;
    const segId = String(seg.id);
    console.log(`[SegmentRowTable] Restaurando audio máster original de IA para segmento ${segId}...`);
    setAdjustingId(segId);
    try {
      const res = await api.resetRawAudios(currentProject, segId);
      useProjectStore.getState().setSegments(res.metadata);
      setLocalRatios((prev) => ({ ...prev, [segId]: 1.0 }));
      console.log(`[SegmentRowTable] Segmento ${segId} restaurado a máster 1.0x.`);
      onRefreshWaveforms();
    } catch (err: any) {
      console.error(`[SegmentRowTable] Error al restaurar audio del segmento:`, err);
      alert(`Error al restaurar audio original: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setAdjustingId(null);
    }
  };

  // Aplicar todos los cambios de tiempos y recalcular la línea de tiempo completa
  const handleApplyAllTimings = async () => {
    if (!currentProject) return;
    setIsApplyingTimings(true);
    console.log(`[SegmentRowTable] Enviando aplicación y recálculo de tiempos para ${segments.length} segmentos...`);
    try {
      const payload = segments.map((s) => ({
        id: String(s.id),
        start_ms: localStarts[String(s.id)] ?? s.start_ms,
      }));
      const res = await api.updateProjectTimings(currentProject, payload);
      useProjectStore.getState().setSegments(res.metadata);

      // Sincronizar inputs locales con los valores recalculados confirmados por el servidor
      const freshStarts: Record<string, number> = {};
      const freshRatios: Record<string, number> = {};
      res.metadata.forEach((s) => {
        const sid = String(s.id);
        freshStarts[sid] = s.start_ms;
        freshRatios[sid] = s.speed_ratio ?? s.current_speed_ratio ?? 1.0;
      });
      setLocalStarts(freshStarts);
      setLocalRatios(freshRatios);

      console.log(`[SegmentRowTable] Recálculo completado y sincronizado con éxito.`);
      onRefreshWaveforms();
    } catch (err: any) {
      console.error(`[SegmentRowTable] Error al aplicar tiempos:`, err);
      alert(`Error al aplicar tiempos: ${err.message}`);
    } finally {
      setIsApplyingTimings(false);
    }
  };

  // Delete currently selected segment
  const handleDeleteSelected = async () => {
    if (!currentProject || !selectedSegmentId) return;
    if (!confirm(`¿Eliminar el segmento [${selectedSegmentId}]?`)) return;

    try {
      const res = await api.deleteSegment(currentProject, selectedSegmentId);
      useProjectStore.getState().setSegments(res.metadata);
      setSelectedSegmentId(null);
      onRefreshWaveforms();
    } catch (err: any) {
      alert(`Error al eliminar: ${err.message}`);
    }
  };

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden text-xs">
      {/* Table Header Bar */}
      <div className="px-4 py-3 bg-neutral-950 border-b border-neutral-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-bold text-neutral-200">Ajuste Fino de Segmentos ({segments.length})</span>
          {overlapAnalysis.hasOverlaps ? (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1 animate-pulse">
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              <span>{overlapAnalysis.totalOverlaps} {overlapAnalysis.totalOverlaps === 1 ? 'traslape' : 'traslapes'}</span>
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
              <Check className="w-3 h-3" />
              <span>Sin traslapes</span>
            </span>
          )}
          <span className="text-[11px] text-neutral-500 font-normal">
            Modifica tiempos de inicio, ratios de velocidad y pulsa "Ajustar"
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {selectedSegmentId && (
            <button
              onClick={handleDeleteSelected}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-600/80 hover:bg-rose-500 text-white transition flex items-center gap-1.5 shadow"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Eliminar [{selectedSegmentId}]</span>
            </button>
          )}

          <button
            onClick={handleApplyAllTimings}
            disabled={isApplyingTimings}
            className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-sky-600 hover:bg-sky-500 text-white transition flex items-center gap-1.5 shadow-md shadow-sky-600/20 disabled:opacity-50"
          >
            {isApplyingTimings ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>Aplicar y Recalcular Tiempos</span>
          </button>
        </div>
      </div>

      {/* Rows Container */}
      <div className="max-h-72 overflow-y-auto divide-y divide-neutral-800/80 p-2 space-y-1">
        {segments.map((seg, idx) => {
          const segId = String(seg.id);
          const isSelected = selectedSegmentId === segId;
          const isPlaying = playingSegmentId === segId;
          const isAdjusting = adjustingId === segId;
          const ratio = localRatios[segId] ?? seg.speed_ratio ?? seg.current_speed_ratio ?? 1.0;
          const startVal = localStarts[segId] ?? seg.start_ms;

          const isGoodRatio = ratio >= 0.90 && ratio <= 1.20;

          const colInfo = overlapAnalysis.segmentCollisions[segId];
          const hasOutgoingOverlap = Boolean(colInfo && colInfo.outgoing.length > 0);
          const hasIncomingOverlap = Boolean(colInfo && colInfo.incoming.length > 0);
          const isOverlapping = hasOutgoingOverlap || hasIncomingOverlap;

          return (
            <div
              key={seg.id}
              onClick={() => setSelectedSegmentId(segId)}
              className={`p-2.5 rounded-xl border transition flex flex-wrap items-center justify-between gap-3 ${
                isSelected
                  ? 'border-yellow-400 bg-yellow-400/10 shadow-sm shadow-yellow-400/10'
                  : isOverlapping
                  ? 'border-rose-500/80 bg-rose-950/25 shadow-sm shadow-rose-500/10 hover:border-rose-400'
                  : 'border-neutral-800/60 bg-neutral-950/60 hover:border-neutral-700'
              }`}
            >
              {/* Left: Play button, Filename & Text */}
              <div className="flex items-center gap-3 flex-1 min-w-[320px]">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleTogglePlay(seg);
                  }}
                  className={`w-7 h-7 rounded-lg flex items-center justify-center transition ${
                    isPlaying ? 'bg-amber-500 text-black' : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-200'
                  }`}
                  title={isPlaying ? 'Detener' : 'Reproducir fragmento'}
                >
                  {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 ml-0.5" />}
                </button>

                <div className="flex flex-col">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[11px] font-bold text-neutral-300">
                    {seg.filename} <span className="text-neutral-500">[{seg.id}]</span>
                  </span>
                    {hasOutgoingOverlap && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1 shrink-0 animate-pulse"
                        title={`Este audio se monta ${Math.round(colInfo.outgoing[0].overlapMs)}ms sobre el segmento [${colInfo.outgoing[0].otherId}].`}
                      >
                        <AlertTriangle className="w-3 h-3 text-rose-400" />
                        <span>Traslape: +{Math.round(colInfo.outgoing[0].overlapMs)}ms con [{colInfo.outgoing[0].otherId}]</span>
                      </span>
                    )}
                    {!hasOutgoingOverlap && hasIncomingOverlap && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-500/10 text-rose-400/90 border border-rose-500/20 flex items-center gap-1 shrink-0"
                        title={`Invadido ${Math.round(colInfo.incoming[0].overlapMs)}ms por el segmento [${colInfo.incoming[0].otherId}].`}
                      >
                        <AlertTriangle className="w-3 h-3 text-rose-400" />
                        <span>Invadido por [{colInfo.incoming[0].otherId}]</span>
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex-1">
                  <input
                    type="text"
                    value={seg.translated}
                    onChange={(e) => updateSegment(seg.id, { translated: e.target.value })}
                    onBlur={saveCurrentMetadata}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full bg-neutral-900 border border-neutral-800 focus:border-sky-500 rounded px-2 py-1 text-xs text-emerald-300 outline-none"
                    placeholder="Texto doblado..."
                  />
                </div>
              </div>

              {/* Right: Timing & Ratio Numerical Inputs */}
              <div className="flex items-center gap-3 font-mono text-xs">
                {/* Inicio (ms) */}
                <div className="flex items-center gap-1.5">
                  <span className="text-neutral-400">Inicio:</span>
                  <input
                    type="number"
                    value={startVal}
                    onChange={(e) =>
                      setLocalStarts({ ...localStarts, [segId]: Number(e.target.value) })
                    }
                    onClick={(e) => e.stopPropagation()}
                    className="w-20 bg-neutral-900 border border-neutral-800 rounded px-2 py-1 text-neutral-200 text-right outline-none focus:border-sky-500"
                  />
                  <span className="text-neutral-500">ms</span>
                </div>

                {/* Fin (ms) */}
                <div className="flex items-center gap-1 text-neutral-400">
                  <span>Fin:</span>
                  <span className="text-neutral-300 font-bold">{seg.end_ms}ms</span>
                </div>

                {/* Ratio (Speed) */}
                <div className="flex items-center gap-1.5">
                  <span className="text-neutral-400">Ratio:</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.5"
                    max="3.0"
                    value={ratio}
                    onChange={(e) =>
                      setLocalRatios({ ...localRatios, [segId]: Number(e.target.value) })
                    }
                    onClick={(e) => e.stopPropagation()}
                    className={`w-16 bg-neutral-900 border rounded px-1.5 py-1 text-right font-bold outline-none focus:border-sky-500 ${
                      isGoodRatio
                        ? 'border-emerald-500/40 text-emerald-400'
                        : 'border-amber-500/40 text-amber-400'
                    }`}
                  />
                  <span className="text-neutral-500">x</span>
                </div>

                {/* Botón Ajustar Ratio con FFmpeg */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAdjustRatio(seg);
                  }}
                  disabled={isAdjusting}
                  className="px-2.5 py-1 rounded bg-sky-600 hover:bg-sky-500 text-white font-bold transition flex items-center gap-1 disabled:opacity-50"
                  title="Aplica time-stretching con FFmpeg con este ratio exacto sobre este fragmento"
                >
                  {isAdjusting ? (
                    <RefreshCw className="w-3 h-3 animate-spin" />
                  ) : (
                    <Zap className="w-3 h-3" />
                  )}
                  <span>Ajustar</span>
                </button>

                {/* Botón Restaurar Audio Original de IA (1.0x) */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleResetSegmentAudio(seg);
                  }}
                  disabled={isAdjusting}
                  className="p-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-amber-400 transition flex items-center justify-center disabled:opacity-50 border border-neutral-700"
                  title="Restaura este segmento a su audio virgen original de la IA (1.0x)"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

