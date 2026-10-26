import React, { useState, useEffect, useCallback } from 'react';
import { useProjectStore } from '../stores/useProjectStore';
import { TimelineCanvas } from '../components/studio/TimelineCanvas';
import { SegmentRowTable } from '../components/studio/SegmentRowTable';
import { useWebAudio } from '../hooks/useWebAudio';
import { SilenceGap } from '../types';
import * as api from '../api/client';
import {
  Play,
  Pause,
  Square,
  Volume2,
  VolumeX,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Scissors,
  Split,
  Download,
  Sparkles,
  AlertTriangle,
  Check,
} from 'lucide-react';
import { OverlapAnalysisResult } from '../utils/overlapDetector';

export const StudioTab: React.FC = () => {
  const {
    currentProject,
    segments,
    audioDurationMs,
    selectedSegmentId,
    setSelectedSegmentId,
    setSegments,
    revertToMaster,
  } = useProjectStore();

  const [zoom, setZoom] = useState(() => {
    try {
      const saved = localStorage.getItem('studio_zoom');
      return saved ? Math.max(10, Math.min(320, Number(saved))) : 40;
    } catch {
      return 40;
    }
  }); // Pixels per second

  useEffect(() => {
    try {
      localStorage.setItem('studio_zoom', String(zoom));
    } catch {}
  }, [zoom]);
  const [viewOffsetMs, setViewOffsetMs] = useState(0);
  const [activeTool, setActiveTool] = useState<'cursor' | 'razor'>('cursor');

  // Waveforms and Silences State
  const [origPeaks, setOrigPeaks] = useState<number[]>([]);
  const [dubPeaks, setDubPeaks] = useState<number[]>([]);
  const [silences, setSilences] = useState<SilenceGap[]>([]);
  const [overlapResult, setOverlapResult] = useState<OverlapAnalysisResult>({
    hasOverlaps: false,
    totalOverlaps: 0,
    collisionRegions: [],
    segmentCollisions: {},
  });

  // Export Modal State
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportType, setExportType] = useState<'video' | 'audio'>('video');
  const [outputPath, setOutputPath] = useState('');
  const [isExporting, setIsExporting] = useState(false);

  // Audio URLs & Versioning for Cache-busting
  const [dubbedAudioVersion, setDubbedAudioVersion] = useState(Date.now());
  const originalAudioUrl = currentProject ? `/api/audio/${currentProject}/original` : undefined;
  const dubbedAudioUrl = currentProject ? `/api/audio/${currentProject}/dubbed?v=${dubbedAudioVersion}` : undefined;

  // Web Audio Hook (Dual Multitrack Playback)
  const {
    isPlaying,
    currentTimeMs,
    play,
    pause,
    seek,
    stop,
    volOrig,
    setVolOrig,
    volDub,
    setVolDub,
    isMuteOrig,
    setIsMuteOrig,
    isMuteDub,
    setIsMuteDub,
  } = useWebAudio(originalAudioUrl, dubbedAudioUrl);

  // Fetch all waveforms (both tracks) and silences
  const loadWaveforms = useCallback(async () => {
    if (!currentProject) return;
    try {
      console.log(`[StudioTab] Recargando formas de onda para '${currentProject}'...`);
      const data = await api.getAllWaveforms(currentProject, 1600);
      setOrigPeaks(data.orig_peaks || []);
      setDubPeaks(data.dub_peaks || []);
      setSilences(data.silences || []);
      const newVersion = Date.now();
      setDubbedAudioVersion(newVersion);
      console.log(`[StudioTab] Formas de onda y versión de mezcla sincronizadas: ${newVersion}`);
    } catch (err) {
      console.error('[StudioTab] Error fetching all waveforms', err);
    }
  }, [currentProject]);

  useEffect(() => {
    loadWaveforms();
    if (currentProject) {
      setOutputPath(`F:\\Desarrollo\\${currentProject}_doblado.mp4`);
    }
  }, [currentProject, loadWaveforms]);

  // Spacebar toggle for Play/Pause
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.code === 'Space' &&
        (e.target as HTMLElement).tagName !== 'TEXTAREA' &&
        (e.target as HTMLElement).tagName !== 'INPUT'
      ) {
        e.preventDefault();
        if (isPlaying) pause();
        else play();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isPlaying, play, pause]);

  // Zoom controls
  const handleZoomIn = () => setZoom((z) => Math.min(250, z * 1.3));
  const handleZoomOut = () => setZoom((z) => Math.max(10, z / 1.3));
  const handleResetZoom = () => {
    setZoom(40);
    setViewOffsetMs(0);
  };

  // Splitting operations
  const handleSplitSegment = async (id: string, cutMs: number) => {
    if (!currentProject) return;
    try {
      const res = await api.autoSplitSegment(currentProject, id);
      setSegments(res.metadata);
      loadWaveforms();
    } catch (err: any) {
      alert(`Error al dividir: ${err.message}`);
    }
  };

  const handleAutoSplitSelected = async () => {
    if (!currentProject || !selectedSegmentId) return;
    try {
      const res = await api.autoSplitSegment(currentProject, selectedSegmentId);
      setSegments(res.metadata);
      loadWaveforms();
    } catch (err: any) {
      alert(`Error al auto-dividir: ${err.message}`);
    }
  };

  const handleAutoSplitAll = async () => {
    if (!currentProject) return;
    try {
      const res = await api.autoSplitAllSegments(currentProject);
      setSegments(res.metadata);
      loadWaveforms();
      alert(`¡Se dividieron ${res.split_count} segmentos largos por pausas y comas!`);
    } catch (err: any) {
      alert(`Error al auto-dividir todos: ${err.message}`);
    }
  };

  const handleResetAllRawAudios = async () => {
    if (!currentProject) return;
    if (
      !confirm(
        '¿Deseas restaurar TODOS los audios a sus versiones originales de la IA (1.0x)?\n\nSe eliminarán todos los cambios de velocidad y estiramientos previos.'
      )
    ) {
      return;
    }
    try {
      console.log(`[StudioTab] Solicitando reset total a másters raw para proyecto '${currentProject}'...`);
      const res = await api.resetRawAudios(currentProject);
      setSegments(res.metadata);
      loadWaveforms();
      alert(`¡Éxito! Se restauraron ${res.restored_count} audios al máster original de la IA (1.0x).`);
    } catch (err: any) {
      console.error('[StudioTab] Error al restaurar audios originales:', err);
      alert(`Error al restaurar audios: ${err?.response?.data?.detail || err.message}`);
    }
  };

  const handleResetScriptMaster = async () => {
    if (
      !confirm(
        '⚠️ ADVERTENCIA: Esta acción restaurará la estructura inicial del guion de antes de realizar cortes con Whisper o Cuchilla.\n\n¿Estás seguro de que deseas deshacer todas las divisiones de frases?'
      )
    ) {
      return;
    }
    await revertToMaster();
    loadWaveforms();
  };

  const handleExport = async () => {
    if (!currentProject || !outputPath.trim()) return;
    setIsExporting(true);
    try {
      await api.exportProject(
        currentProject,
        outputPath.trim(),
        exportType,
        volOrig,
        isMuteOrig,
        volDub,
        isMuteDub
      );
      setShowExportModal(false);
    } catch (err: any) {
      alert(`Error al exportar: ${err.message}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handleScrollToFirstCollision = () => {
    if (!overlapResult.collisionRegions || overlapResult.collisionRegions.length === 0) return;
    const firstCol = overlapResult.collisionRegions[0];
    setSelectedSegmentId(firstCol.segIdA);
    setViewOffsetMs(Math.max(0, firstCol.startMs - 2000));
    seek(firstCol.startMs);
  };

  // Format timecode (mm:ss.ms)
  const formatTimecode = (ms: number) => {
    const totalSecs = Math.max(0, ms) / 1000;
    const mins = Math.floor(totalSecs / 60);
    const secs = Math.floor(totalSecs % 60);
    const millis = Math.floor((totalSecs % 1) * 1000);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
  };

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-4 pb-12">
      {/* Top Toolbar */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-3 flex flex-wrap items-center justify-between gap-4">
        {/* Tool switches */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-neutral-950 p-1 rounded-lg border border-neutral-800">
            <button
              onClick={() => setActiveTool('cursor')}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                activeTool === 'cursor' ? 'bg-sky-500 text-white' : 'text-neutral-400 hover:text-white'
              }`}
            >
              Cursor
            </button>
            <button
              onClick={() => setActiveTool('razor')}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition flex items-center gap-1 ${
                activeTool === 'razor' ? 'bg-sky-500 text-white' : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Scissors className="w-3.5 h-3.5" />
              <span>Cuchilla</span>
            </button>
          </div>

          <button
            onClick={handleAutoSplitSelected}
            disabled={!selectedSegmentId}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white transition flex items-center gap-1 disabled:opacity-40"
          >
            <Split className="w-3.5 h-3.5" />
            <span>Auto-dividir frase</span>
          </button>

          <button
            onClick={handleAutoSplitAll}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Auto-dividir todas</span>
          </button>

          <button
            onClick={handleResetAllRawAudios}
            className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-amber-600/90 hover:bg-amber-500 text-white transition flex items-center gap-1.5 shadow-sm shadow-amber-600/30"
            title="Restaura todos los audios a sus versiones vírgenes de la IA (1.0x) y reconstruye la mezcla"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Audios Originales</span>
          </button>

          <button
            onClick={handleResetScriptMaster}
            className="px-2.5 py-1.5 rounded-lg text-[11px] font-normal bg-neutral-900 border border-neutral-800 hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 transition flex items-center gap-1"
            title="Deshace las divisiones de cortes y restaura las secciones originales del Paso 1"
          >
            <span>Deshacer Cortes</span>
          </button>
        </div>

        {/* Overlap Status / Quick Navigation Button */}
        {overlapResult.hasOverlaps ? (
          <button
            onClick={handleScrollToFirstCollision}
            className="px-3 py-1.5 rounded-lg text-xs font-bold bg-rose-600/25 hover:bg-rose-600/40 border border-rose-500/60 text-rose-300 transition flex items-center gap-1.5 shadow-sm shadow-rose-600/20 animate-pulse"
            title="Haz clic para saltar al primer traslape y enfocarlo en la línea de tiempo"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
            <span>{overlapResult.totalOverlaps} {overlapResult.totalOverlaps === 1 ? 'traslape detectado' : 'traslapes detectados'}</span>
          </button>
        ) : (
          <div className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1">
            <Check className="w-3.5 h-3.5" />
            <span>0 traslapes</span>
          </div>
        )}

        {/* Zoom controls & Export button */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-neutral-950 p-1 rounded-lg border border-neutral-800">
            <button
              onClick={handleZoomOut}
              className="p-1 rounded text-neutral-400 hover:text-white"
              title="Reducir zoom"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleResetZoom}
              className="px-2 py-0.5 text-[10px] font-mono text-neutral-400 hover:text-white"
            >
              {Math.round((zoom / 40) * 100)}%
            </button>
            <button
              onClick={handleZoomIn}
              className="p-1 rounded text-neutral-400 hover:text-white"
              title="Aumentar zoom"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={() => setShowExportModal(true)}
            className="px-4 py-2 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-emerald-600/20"
          >
            <Download className="w-4 h-4" />
            <span>Exportar Mezcla</span>
          </button>
        </div>
      </div>

      {/* Multitrack Canvas Timeline with Dual Waveforms and Silence Gaps */}
      <div className="space-y-2">
        <TimelineCanvas
          segments={segments}
          totalDurationMs={audioDurationMs}
          playheadMs={currentTimeMs}
          zoom={zoom}
          viewOffsetMs={viewOffsetMs}
          activeTool={activeTool}
          selectedSegmentId={selectedSegmentId}
          onSeek={seek}
          onSelectSegment={setSelectedSegmentId}
          onSplitSegment={handleSplitSegment}
          onViewOffsetChange={setViewOffsetMs}
          origPeaks={origPeaks}
          dubPeaks={dubPeaks}
          silences={silences}
          collisionRegions={overlapResult.collisionRegions}
          segmentCollisions={overlapResult.segmentCollisions}
        />

        {/* Horizontal Timeline Scrollbar */}
        <div className="px-2">
          <input
            type="range"
            min={0}
            max={Math.max(1, audioDurationMs - 10000)}
            value={viewOffsetMs}
            onChange={(e) => setViewOffsetMs(Number(e.target.value))}
            className="w-full accent-sky-500 h-1.5 bg-neutral-800 rounded-lg cursor-pointer"
          />
        </div>
      </div>

      {/* Transport Bar & Volume Sliders */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-6">
        {/* Playback Controls & Timecode */}
        <div className="flex items-center gap-4">
          <button
            onClick={isPlaying ? pause : play}
            className="w-10 h-10 rounded-full bg-sky-500 hover:bg-sky-400 text-white flex items-center justify-center transition shadow-lg shadow-sky-500/20"
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
          </button>

          <button
            onClick={stop}
            className="p-2.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-300 hover:text-white transition"
            title="Detener y volver al inicio"
          >
            <Square className="w-4 h-4" />
          </button>

          <div className="font-mono text-sm font-bold tracking-wider text-neutral-200 bg-neutral-950 px-3 py-1.5 rounded-lg border border-neutral-800">
            <span className="text-yellow-400">{formatTimecode(currentTimeMs)}</span>
            <span className="text-neutral-600"> / </span>
            <span className="text-neutral-400">{formatTimecode(audioDurationMs)}</span>
          </div>
        </div>

        {/* Track Volume & Mute Controls */}
        <div className="flex items-center gap-6 text-xs">
          {/* Original Track */}
          <div className="flex items-center gap-2 bg-neutral-950 px-3 py-1.5 rounded-lg border border-neutral-800">
            <span className="font-bold text-sky-400">Pista Original:</span>
            <button
              onClick={() => setIsMuteOrig(!isMuteOrig)}
              className={`p-1 rounded ${isMuteOrig ? 'text-rose-400' : 'text-neutral-400 hover:text-white'}`}
            >
              {isMuteOrig ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
            </button>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={volOrig}
              onChange={(e) => setVolOrig(Number(e.target.value))}
              className="w-16 accent-sky-500 h-1 bg-neutral-800 cursor-pointer"
            />
            <span className="font-mono text-[10px] text-neutral-400 w-8">{Math.round(volOrig * 100)}%</span>
          </div>

          {/* Dubbed Track */}
          <div className="flex items-center gap-2 bg-neutral-950 px-3 py-1.5 rounded-lg border border-neutral-800">
            <span className="font-bold text-orange-400">Pista Doblada:</span>
            <button
              onClick={() => setIsMuteDub(!isMuteDub)}
              className={`p-1 rounded ${isMuteDub ? 'text-rose-400' : 'text-neutral-400 hover:text-white'}`}
            >
              {isMuteDub ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
            </button>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={volDub}
              onChange={(e) => setVolDub(Number(e.target.value))}
              className="w-16 accent-orange-500 h-1 bg-neutral-800 cursor-pointer"
            />
            <span className="font-mono text-[10px] text-neutral-400 w-8">{Math.round(volDub * 100)}%</span>
          </div>
        </div>
      </div>

      {/* Segment Fine Tuning Table (SegmentRowTable) */}
      <SegmentRowTable onRefreshWaveforms={loadWaveforms} onOverlapsChange={setOverlapResult} />

      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Download className="w-5 h-5 text-emerald-400" />
              <span>Exportar Mezcla Final</span>
            </h3>

            <div className="space-y-3 text-sm">
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">Tipo de Exportación</label>
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 text-xs text-neutral-200 cursor-pointer">
                    <input
                      type="radio"
                      checked={exportType === 'video'}
                      onChange={() => setExportType('video')}
                      className="accent-sky-500 cursor-pointer"
                    />
                    <span>Video Final (.mp4)</span>
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-neutral-200 cursor-pointer">
                    <input
                      type="radio"
                      checked={exportType === 'audio'}
                      onChange={() => setExportType('audio')}
                      className="accent-sky-500 cursor-pointer"
                    />
                    <span>Solo Audio (.wav / .mp3)</span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">Ruta del Archivo de Salida</label>
                <input
                  type="text"
                  value={outputPath}
                  onChange={(e) => setOutputPath(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-white outline-none focus:border-sky-500 font-mono text-xs"
                />
              </div>

              <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800 space-y-2 text-xs">
                <span className="font-semibold text-neutral-300">Balance de Mezcla:</span>
                <div className="flex items-center justify-between text-neutral-400">
                  <span>Volumen Original: {isMuteOrig ? 'Silenciado' : `${Math.round(volOrig * 100)}%`}</span>
                  <span>Volumen Doblaje: {isMuteDub ? 'Silenciado' : `${Math.round(volDub * 100)}%`}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setShowExportModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-neutral-400 hover:text-white"
              >
                Cancelar
              </button>
              <button
                onClick={handleExport}
                disabled={isExporting}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition disabled:opacity-50"
              >
                {isExporting ? 'Exportando...' : 'Iniciar Exportación'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
