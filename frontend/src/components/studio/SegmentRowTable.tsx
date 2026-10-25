import React, { useState, useEffect } from 'react';
import { Segment } from '../../types';
import { useProjectStore } from '../../stores/useProjectStore';
import * as api from '../../api/client';
import { Play, Pause, Save, Trash2, Zap, RotateCcw, Check, RefreshCw } from 'lucide-react';

interface Props {
  onRefreshWaveforms: () => void;
}

export const SegmentRowTable: React.FC<Props> = ({ onRefreshWaveforms }) => {
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

  // Play individual segment slice
  const handleTogglePlay = (seg: Segment) => {
    const segId = String(seg.id);
    if (playingSegmentId === segId && activeAudio) {
      activeAudio.pause();
      setActiveAudio(null);
      setPlayingSegmentId(null);
      return;
    }

    if (activeAudio) {
      activeAudio.pause();
    }

    if (!currentProject) return;
    const url = `/api/audio/${currentProject}/segment/${seg.filename}`;
    const audio = new Audio(url);
    audio.onended = () => setPlayingSegmentId(null);
    audio.onerror = () => setPlayingSegmentId(null);
    audio.play().catch(() => setPlayingSegmentId(null));

    setActiveAudio(audio);
    setPlayingSegmentId(segId);
  };

  // Adjust custom ratio with FFmpeg atempo
  const handleAdjustRatio = async (seg: Segment) => {
    if (!currentProject) return;
    const segId = String(seg.id);
    const r = localRatios[segId] ?? seg.speed_ratio ?? seg.current_speed_ratio ?? 1.0;

    setAdjustingId(segId);
    try {
      const res = await api.adjustSegmentRatio(currentProject, segId, r);
      const confirmedRatio = res.segment.speed_ratio ?? res.segment.current_speed_ratio ?? r;
      updateSegment(seg.id, {
        clip_duration_ms: res.segment.clip_duration_ms,
        speed_ratio: confirmedRatio,
        current_speed_ratio: confirmedRatio,
        is_manual_ratio: true,
      });
      setLocalRatios((prev) => ({ ...prev, [segId]: confirmedRatio }));
      onRefreshWaveforms();
    } catch (err: any) {
      alert(`Error al ajustar velocidad: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setAdjustingId(null);
    }
  };

  // Apply all start_ms changes and recalculate project timeline
  const handleApplyAllTimings = async () => {
    if (!currentProject) return;
    setIsApplyingTimings(true);
    try {
      const payload = segments.map((s) => ({
        id: String(s.id),
        start_ms: localStarts[String(s.id)] ?? s.start_ms,
      }));
      const res = await api.updateProjectTimings(currentProject, payload);
      useProjectStore.getState().setSegments(res.metadata);
      onRefreshWaveforms();
    } catch (err: any) {
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
        <div className="flex items-center gap-2">
          <span className="font-bold text-neutral-200">Ajuste Fino de Segmentos ({segments.length})</span>
          <span className="text-[11px] text-neutral-500 font-normal">
            Modifica tiempos de inicio, ratios de velocidad y pulsa "Ajustar"
          </span>
        </div>

        <div className="flex items-center gap-2">
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

          return (
            <div
              key={seg.id}
              onClick={() => setSelectedSegmentId(segId)}
              className={`p-2.5 rounded-xl border transition flex flex-wrap items-center justify-between gap-3 ${
                isSelected
                  ? 'border-yellow-400 bg-yellow-400/10 shadow-sm shadow-yellow-400/10'
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
                  <span className="font-mono text-[11px] font-bold text-neutral-300">
                    {seg.filename} <span className="text-neutral-500">[{seg.id}]</span>
                  </span>
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

                {/* Ajustar Button (FFmpeg atempo) */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAdjustRatio(seg);
                  }}
                  disabled={isAdjusting}
                  className="px-2.5 py-1 rounded bg-sky-600 hover:bg-sky-500 text-white font-bold transition flex items-center gap-1 disabled:opacity-50"
                  title="Aplica time-stretching con FFmpeg con este ratio exacto"
                >
                  {isAdjusting ? (
                    <RefreshCw className="w-3 h-3 animate-spin" />
                  ) : (
                    <Zap className="w-3 h-3" />
                  )}
                  <span>Ajustar</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

