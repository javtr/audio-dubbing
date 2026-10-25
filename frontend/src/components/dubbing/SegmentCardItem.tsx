import React, { useState } from 'react';
import { Segment, ReferenceItem } from '../../types';
import { useProjectStore } from '../../stores/useProjectStore';
import * as api from '../../api/client';
import { Play, Pause, RefreshCw, Volume2, Sparkles, Check, AlertCircle } from 'lucide-react';

interface Props {
  segment: Segment;
  index: number;
}

export const SegmentCardItem: React.FC<Props> = ({ segment, index }) => {
  const { currentProject, references, updateSegment, saveCurrentMetadata } = useProjectStore();

  const [selectedRef, setSelectedRef] = useState('ref_Conversational');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPlayingOrig, setIsPlayingOrig] = useState(false);
  const [isPlayingDub, setIsPlayingDub] = useState(false);

  const audioOrigUrl = currentProject ? `/api/audio/${currentProject}/original` : '';
  const audioDubUrl = currentProject && segment.clip_duration_ms && segment.clip_duration_ms > 0
    ? `/api/audio/${currentProject}/segment/${segment.filename}`
    : '';

  const targetSpan = segment.end_ms - segment.start_ms;
  const targetSec = (targetSpan / 1000).toFixed(1);
  const clipSec = segment.clip_duration_ms ? (segment.clip_duration_ms / 1000).toFixed(1) : null;
  const ratio = segment.current_speed_ratio || 1.0;

  // Speed color badge
  const isGoodSpeed = ratio >= 0.90 && ratio <= 1.20;
  const isWarningSpeed = (ratio > 1.20 && ratio <= 1.35) || ratio < 0.90;

  const handleGenerate = async () => {
    if (!currentProject) return;
    setIsGenerating(true);
    try {
      const res = await api.generateSingleTTS(currentProject, segment.id, selectedRef);
      updateSegment(segment.id, {
        clip_duration_ms: res.clip_duration_ms,
        current_speed_ratio: res.speed_ratio,
      });
      await saveCurrentMetadata();
    } catch (err: any) {
      alert(`Error al generar audio: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const playAudio = (url: string, setPlaying: (val: boolean) => void) => {
    const audio = new Audio(url);
    setPlaying(true);
    audio.onended = () => setPlaying(false);
    audio.onerror = () => setPlaying(false);
    audio.play().catch(() => setPlaying(false));
  };

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 transition hover:border-neutral-700 space-y-3">
      {/* Top Header */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-bold text-neutral-400">#{index + 1}</span>
          <span className="px-2 py-0.5 rounded bg-neutral-800 font-mono text-neutral-300 font-semibold">
            {segment.id}
          </span>
          <span className="text-neutral-500 font-mono">
            {(segment.start_ms / 1000).toFixed(2)}s - {(segment.end_ms / 1000).toFixed(2)}s ({targetSec}s)
          </span>
        </div>

        {/* Speed Ratio Pill */}
        <div className="flex items-center gap-2">
          {clipSec ? (
            <span
              className={`px-2 py-0.5 rounded font-mono font-bold text-xs ${
                isGoodSpeed
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : isWarningSpeed
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
              }`}
              title={`Duración audio generado: ${clipSec}s vs objetivo: ${targetSec}s`}
            >
              {ratio.toFixed(2)}x ({clipSec}s)
            </span>
          ) : (
            <span className="text-neutral-500 italic text-xs">Sin audio generado</span>
          )}
        </div>
      </div>

      {/* Dual Text Columns */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {/* Original Spanish Text */}
        <div className="bg-neutral-950/70 border border-neutral-800/80 rounded-lg p-2.5 text-neutral-300 flex flex-col justify-between">
          <p className="leading-relaxed">{segment.original}</p>
          <div className="pt-2 flex justify-end">
            <span className="text-[10px] text-neutral-500 uppercase tracking-wider font-semibold">Original (ES)</span>
          </div>
        </div>

        {/* Translated Text (Editable) */}
        <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-2.5 flex flex-col justify-between focus-within:border-sky-500/60">
          <textarea
            value={segment.translated}
            onChange={(e) => updateSegment(segment.id, { translated: e.target.value })}
            onBlur={saveCurrentMetadata}
            rows={3}
            className="w-full bg-transparent text-emerald-300 outline-none resize-none leading-relaxed"
          />
          <div className="pt-1 flex justify-end">
            <span className="text-[10px] text-emerald-500/70 uppercase tracking-wider font-semibold">Traducción</span>
          </div>
        </div>
      </div>

      {/* Bottom Actions Bar */}
      <div className="flex items-center justify-between pt-1 border-t border-neutral-800/60 text-xs">
        <div className="flex items-center gap-2">
          {/* Reference selector */}
          <select
            value={selectedRef}
            onChange={(e) => setSelectedRef(e.target.value)}
            className="bg-neutral-950 border border-neutral-800 rounded-lg px-2 py-1 text-neutral-300 outline-none text-xs cursor-pointer"
          >
            {references.map((r) => (
              <option key={r.segmento} value={r.segmento}>
                Voz: {r.tono}
              </option>
            ))}
          </select>

          {/* Reference Audio Preview */}
          <button
            onClick={() => {
              const refObj = references.find((r) => r.segmento === selectedRef);
              if (refObj) playAudio(refObj.audio_url, () => {});
            }}
            className="p-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-400 hover:text-white"
            title="Escuchar audio de muestra de la voz"
          >
            <Volume2 className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          {/* Play Dubbed Audio */}
          {audioDubUrl && (
            <button
              onClick={() => playAudio(audioDubUrl, setIsPlayingDub)}
              className="px-2.5 py-1 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-emerald-400 font-semibold flex items-center gap-1 transition"
            >
              {isPlayingDub ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              <span>Escuchar Doblaje</span>
            </button>
          )}

          {/* Generate Button */}
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="px-3 py-1 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
          >
            {isGenerating ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
            <span>{isGenerating ? 'Generando...' : 'Generar TTS'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
