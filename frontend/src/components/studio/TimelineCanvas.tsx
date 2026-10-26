import React, { useRef, useEffect, useState } from 'react';
import { Segment, SilenceGap } from '../../types';
import { detectOverlaps, CollisionRegion, SegmentCollisionInfo } from '../../utils/overlapDetector';

interface Props {
  segments: Segment[];
  totalDurationMs: number;
  playheadMs: number;
  zoom: number;            // Pixels per second
  viewOffsetMs: number;    // Visible start time in ms
  activeTool: 'cursor' | 'razor';
  selectedSegmentId: string | null;
  onSeek: (ms: number) => void;
  onSelectSegment: (id: string) => void;
  onSplitSegment: (id: string, cutMs: number) => void;
  onViewOffsetChange: (offsetMs: number) => void;
  origPeaks?: number[];    // [min0, max0, min1, max1, ...]
  dubPeaks?: number[];     // [min0, max0, min1, max1, ...]
  silences?: SilenceGap[];
  collisionRegions?: CollisionRegion[];
  segmentCollisions?: Record<string, SegmentCollisionInfo>;
}

export const TimelineCanvas: React.FC<Props> = ({
  segments,
  totalDurationMs,
  playheadMs,
  zoom,
  viewOffsetMs,
  activeTool,
  selectedSegmentId,
  onSeek,
  onSelectSegment,
  onSplitSegment,
  onViewOffsetChange,
  origPeaks = [],
  dubPeaks = [],
  silences = [],
  collisionRegions,
  segmentCollisions,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredSegment, setHoveredSegment] = useState<Segment | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; offset: number }>({ x: 0, offset: 0 });
  const [canvasWidth, setCanvasWidth] = useState(1400);

  // Sincronizar el ancho interno del canvas al contenedor real con 1:1 pixel ratio
  useEffect(() => {
    if (!containerRef.current) return;
    const updateSize = () => {
      if (containerRef.current) {
        const w = containerRef.current.clientWidth;
        if (w > 0 && w !== canvasWidth) {
          setCanvasWidth(w);
        }
      }
    };
    updateSize();
    const ro = new ResizeObserver(updateSize);
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [canvasWidth]);

  const RULER_H = 26;
  const TRACK1_Y = 30;
  const TRACK1_H = 90;
  const TRACK2_Y = 130;
  const TRACK2_H = 90;
  const TOTAL_H = 230;

  // Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Helper conversions
    const msToX = (ms: number) => ((ms - viewOffsetMs) / 1000) * zoom;
    const xToMs = (x: number) => viewOffsetMs + (x / zoom) * 1000;

    // Clear background
    ctx.fillStyle = '#111111';
    ctx.fillRect(0, 0, width, height);

    // ================= 1. TIME RULER & TICKS =================
    ctx.fillStyle = '#1c1c1c';
    ctx.fillRect(0, 0, width, RULER_H);
    ctx.strokeStyle = '#2d2d2d';
    ctx.lineWidth = 1;

    const secStep = zoom > 120 ? 1 : zoom > 50 ? 5 : 10;
    const startSec = Math.floor(viewOffsetMs / 1000);
    const endSec = Math.ceil(xToMs(width) / 1000);

    ctx.fillStyle = '#888888';
    ctx.font = '10px monospace';
    for (let s = startSec; s <= endSec; s += secStep) {
      const x = msToX(s * 1000);
      if (x >= 0 && x <= width) {
        ctx.beginPath();
        ctx.moveTo(x, 14);
        ctx.lineTo(x, RULER_H);
        ctx.stroke();

        const mins = Math.floor(s / 60);
        const secs = s % 60;
        const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        ctx.fillText(timeStr, x + 4, 18);
      }
    }

    // ================= 2. TRACK 1: ORIGINAL AUDIO TRACK =================
    ctx.fillStyle = '#161616';
    ctx.fillRect(0, TRACK1_Y, width, TRACK1_H);
    ctx.strokeStyle = '#282828';
    ctx.strokeRect(0, TRACK1_Y, width, TRACK1_H);

    // Draw Original Audio Waveform (Min/Max Envelope Bars)
    if (origPeaks.length > 0 && totalDurationMs > 0) {
      const midY = TRACK1_Y + TRACK1_H / 2;
      const halfH = TRACK1_H * 0.44;
      const numBins = Math.floor(origPeaks.length / 2);

      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.6;
      ctx.beginPath();

      for (let i = 0; i < numBins; i++) {
        const pointMs = (i / numBins) * totalDurationMs;
        const x = msToX(pointMs);
        if (x < -2 || x > width + 2) continue;

        const minVal = origPeaks[i * 2];
        const maxVal = origPeaks[i * 2 + 1];

        const yTop = midY - maxVal * halfH;
        const yBottom = midY - minVal * halfH;

        ctx.moveTo(x, yTop);
        ctx.lineTo(x, Math.max(yTop + 1.2, yBottom));
      }
      ctx.stroke();
    }

    // Original Section Division Cut Marks
    segments.forEach((seg) => {
      const sX = msToX(seg.orig_start_ms !== undefined ? seg.orig_start_ms : seg.start_ms);
      const eX = msToX(seg.orig_end_ms !== undefined ? seg.orig_end_ms : seg.end_ms);
      if (sX >= 0 && sX <= width) {
        ctx.strokeStyle = '#0284c7';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(sX, TRACK1_Y);
        ctx.lineTo(sX, TRACK1_Y + TRACK1_H);
        ctx.stroke();
      }
      if (eX >= 0 && eX <= width) {
        ctx.strokeStyle = '#0284c7';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(eX, TRACK1_Y);
        ctx.lineTo(eX, TRACK1_Y + TRACK1_H);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    });

    // Track 1 Header Badge
    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.fillRect(8, TRACK1_Y + 6, 120, 20);
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText('Pista Original (ES)', 14, TRACK1_Y + 20);

    // ================= 3. TRACK 2: DUBBED AUDIO TRACK =================
    ctx.fillStyle = '#161616';
    ctx.fillRect(0, TRACK2_Y, width, TRACK2_H);
    ctx.strokeStyle = '#282828';
    ctx.strokeRect(0, TRACK2_Y, width, TRACK2_H);

    // Draw Dubbed Audio Waveform (Min/Max Envelope Bars)
    if (dubPeaks.length > 0 && totalDurationMs > 0) {
      const midY = TRACK2_Y + TRACK2_H / 2;
      const halfH = TRACK2_H * 0.44;
      const numBins = Math.floor(dubPeaks.length / 2);

      ctx.strokeStyle = '#ff7f0e';
      ctx.lineWidth = 1.6;
      ctx.beginPath();

      for (let i = 0; i < numBins; i++) {
        const pointMs = (i / numBins) * totalDurationMs;
        const x = msToX(pointMs);
        if (x < -2 || x > width + 2) continue;

        const minVal = dubPeaks[i * 2];
        const maxVal = dubPeaks[i * 2 + 1];

        const yTop = midY - maxVal * halfH;
        const yBottom = midY - minVal * halfH;

        ctx.moveTo(x, yTop);
        ctx.lineTo(x, Math.max(yTop + 1.2, yBottom));
      }
      ctx.stroke();
    }

    // ================= 4. DEAD SILENCE GAPS (>= 4.0s) =================
    silences.forEach((sil) => {
      const sX = msToX(sil.start_ms);
      const eX = msToX(sil.end_ms);
      if (eX < 0 || sX > width) return;

      const spanW = Math.max(3, eX - sX);
      const isCritical = sil.level === 'critical'; // > 10s: Magenta neon, 4-10s: Orange

      const faceColor = isCritical ? 'rgba(217, 70, 239, 0.45)' : 'rgba(234, 88, 12, 0.40)';
      const edgeColor = isCritical ? '#f43f5e' : '#f97316';
      const badgeBg = isCritical ? '#d946ef' : '#ea580c';

      // Shaded background
      ctx.fillStyle = faceColor;
      ctx.fillRect(sX, TRACK2_Y + 2, spanW, TRACK2_H - 4);

      // Hatched stripes (//)
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let hX = sX; hX < sX + spanW; hX += 8) {
        ctx.moveTo(hX, TRACK2_Y + TRACK2_H - 2);
        ctx.lineTo(Math.min(hX + 12, sX + spanW), TRACK2_Y + 2);
      }
      ctx.stroke();

      // Border lines
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 2]);
      ctx.strokeRect(sX, TRACK2_Y + 2, spanW, TRACK2_H - 4);
      ctx.setLineDash([]);

      // Floating Duration Badge (+X.Xs)
      if (spanW > 30) {
        const badgeX = sX + spanW / 2;
        const badgeY = TRACK2_Y + 20;
        const text = `+${sil.dur_s}s`;

        ctx.fillStyle = badgeBg;
        ctx.beginPath();
        ctx.roundRect(badgeX - 18, badgeY - 10, 36, 16, 4);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(text, badgeX, badgeY + 2);
        ctx.textAlign = 'left';
      }
    });

    // ================= 5. OVERLAP & COLLISION REGIONS (Pista Doblada) =================
    const dynamicOverlapData = (!collisionRegions || !segmentCollisions)
      ? detectOverlaps(segments)
      : null;
    const activeCollisions = collisionRegions || dynamicOverlapData?.collisionRegions || [];
    const activeSegCollisions = segmentCollisions || dynamicOverlapData?.segmentCollisions || {};

    activeCollisions.forEach((col) => {
      const sX = msToX(col.startMs);
      const eX = msToX(col.endMs);
      if (eX < 0 || sX > width) return;

      const spanW = Math.max(4, eX - sX);

      // Sombreado rojo intenso de advertencia
      ctx.fillStyle = 'rgba(239, 68, 68, 0.45)';
      ctx.fillRect(sX, TRACK2_Y + 2, spanW, TRACK2_H - 4);

      // Rayado diagonal rojo de peligro (///)
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (let hX = sX; hX < sX + spanW; hX += 8) {
        ctx.moveTo(hX, TRACK2_Y + TRACK2_H - 2);
        ctx.lineTo(Math.min(hX + 10, sX + spanW), TRACK2_Y + 2);
      }
      ctx.stroke();

      // Borde punteado rojo neón
      ctx.strokeStyle = '#f43f5e';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 2]);
      ctx.strokeRect(sX, TRACK2_Y + 2, spanW, TRACK2_H - 4);
      ctx.setLineDash([]);

      // Badge flotante con milisegundos de invasión
      if (spanW > 24) {
        const badgeX = sX + spanW / 2;
        const badgeY = TRACK2_Y + TRACK2_H - 16;
        const text = `⚠️ +${Math.round(col.overlapMs)}ms`;

        ctx.fillStyle = '#b91c1c';
        ctx.beginPath();
        ctx.roundRect(badgeX - 25, badgeY - 9, 50, 16, 4);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(text, badgeX, badgeY + 3);
        ctx.textAlign = 'left';
      }
    });

    // ================= 6. SEGMENT BOXES, CUT MARKS & SELECTION =================
    segments.forEach((seg) => {
      const sX = msToX(seg.start_ms);
      const eX = msToX(seg.end_ms);
      if (eX < 0 || sX > width) return;

      const blockW = Math.max(3, eX - sX);
      const isSelected = selectedSegmentId === String(seg.id);
      const ratio = seg.current_speed_ratio || 1.0;
      const hasAudio = seg.clip_duration_ms && seg.clip_duration_ms > 0;
      const colInfo = activeSegCollisions[String(seg.id)];
      const hasCollision = Boolean(colInfo && colInfo.outgoing.length > 0);

      // Collision Warning Outline on Segment Box
      if (hasCollision && !isSelected) {
        ctx.fillStyle = 'rgba(239, 68, 68, 0.15)';
        ctx.fillRect(sX, TRACK2_Y + 2, blockW, TRACK2_H - 4);

        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 2;
        ctx.strokeRect(sX, TRACK2_Y + 2, blockW, TRACK2_H - 4);
      }

      // Selection Highlight (Neon Yellow)
      if (isSelected) {
        ctx.fillStyle = 'rgba(255, 230, 0, 0.22)';
        ctx.fillRect(sX, TRACK2_Y + 2, blockW, TRACK2_H - 4);

        ctx.strokeStyle = hasCollision ? '#ef4444' : '#ffe600';
        ctx.lineWidth = 2.5;
        ctx.strokeRect(sX, TRACK2_Y + 2, blockW, TRACK2_H - 4);
      }

      // Cut marks on boundaries (Dashed Red Lines)
      ctx.strokeStyle = '#ff5252';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([3, 2]);
      ctx.beginPath();
      ctx.moveTo(sX, TRACK2_Y);
      ctx.lineTo(sX, TRACK2_Y + TRACK2_H);
      ctx.moveTo(eX, TRACK2_Y);
      ctx.lineTo(eX, TRACK2_Y + TRACK2_H);
      ctx.stroke();
      ctx.setLineDash([]);

      // Segment text and info pill
      if (blockW > 35) {
        const label = hasCollision
          ? `[${seg.id}] ${ratio.toFixed(2)}x ⚠️ Traslape`
          : `[${seg.id}] ${ratio.toFixed(2)}x`;
        ctx.fillStyle = isSelected ? '#ffe600' : hasCollision ? '#f87171' : '#ffffff';
        ctx.font = 'bold 10px sans-serif';
        ctx.fillText(label, sX + 4, TRACK2_Y + TRACK2_H - 10);

        if (blockW > 80) {
          ctx.fillStyle = hasCollision ? '#fca5a5' : '#a3a3a3';
          ctx.font = '9px sans-serif';
          const textPreview = seg.translated.slice(0, Math.floor(blockW / 7));
          ctx.fillText(textPreview, sX + 4, TRACK2_Y + 36);
        }
      }
    });

    // Track 2 Header Badge
    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.fillRect(8, TRACK2_Y + 6, 125, 20);
    ctx.fillStyle = '#ff7f0e';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText('Pista Doblada (TTS)', 14, TRACK2_Y + 20);

    // ================= 6. PLAYHEAD (SCRUBBER LINE) =================
    const playheadX = msToX(playheadMs);
    if (playheadX >= 0 && playheadX <= width) {
      // Glow
      ctx.strokeStyle = 'rgba(255, 230, 0, 0.35)';
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(playheadX, 0);
      ctx.lineTo(playheadX, height);
      ctx.stroke();

      // Sharp Yellow Scrubber Line
      ctx.strokeStyle = '#ffe600';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(playheadX, 0);
      ctx.lineTo(playheadX, height);
      ctx.stroke();

      // Playhead Top Pointer Arrow
      ctx.fillStyle = '#ffe600';
      ctx.beginPath();
      ctx.moveTo(playheadX - 6, 0);
      ctx.lineTo(playheadX + 6, 0);
      ctx.lineTo(playheadX, 12);
      ctx.closePath();
      ctx.fill();
    }
  }, [segments, totalDurationMs, playheadMs, zoom, viewOffsetMs, selectedSegmentId, origPeaks, dubPeaks, silences, collisionRegions, segmentCollisions, canvasWidth]);

  // Click & Pan Handlers con escalado exacto de coordenadas
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = canvasRef.current && rect.width > 0 ? canvasRef.current.width / rect.width : 1;
    const x = (e.clientX - rect.left) * scaleX;
    const clickedMs = viewOffsetMs + (x / zoom) * 1000;

    if (e.button === 1 || e.altKey) {
      setIsPanning(true);
      panStartRef.current = { x: e.clientX, offset: viewOffsetMs };
      return;
    }

    if (activeTool === 'razor') {
      const target = segments.find((s) => clickedMs >= s.start_ms && clickedMs <= s.end_ms);
      if (target) {
        onSplitSegment(String(target.id), clickedMs);
      }
    } else {
      const target = segments.find((s) => clickedMs >= s.start_ms && clickedMs <= s.end_ms);
      if (target) {
        onSelectSegment(String(target.id));
      }
      onSeek(Math.max(0, clickedMs));
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning) {
      const dx = e.clientX - panStartRef.current.x;
      const dMs = (dx / zoom) * 1000;
      onViewOffsetChange(Math.max(0, panStartRef.current.offset - dMs));
      return;
    }

    const rect = e.currentTarget.getBoundingClientRect();
    const scaleX = canvasRef.current && rect.width > 0 ? canvasRef.current.width / rect.width : 1;
    const x = (e.clientX - rect.left) * scaleX;
    const hoverMs = viewOffsetMs + (x / zoom) * 1000;
    const target = segments.find((s) => hoverMs >= s.start_ms && hoverMs <= s.end_ms);
    setHoveredSegment(target || null);
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  return (
    <div ref={containerRef} className="relative w-full overflow-hidden select-none">
      <canvas
        ref={canvasRef}
        width={canvasWidth}
        height={TOTAL_H}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className={`w-full rounded-xl bg-neutral-900 border border-neutral-800 ${
          activeTool === 'razor' ? 'cursor-crosshair' : 'cursor-pointer'
        }`}
      />

      {/* Hover Info Tooltip */}
      {hoveredSegment && (
        <div className="absolute top-2 right-4 bg-neutral-950/90 border border-neutral-700 rounded-lg px-3 py-1.5 text-xs text-neutral-200 pointer-events-none shadow-xl max-w-sm">
          <span className="font-bold text-yellow-400">[{hoveredSegment.id}]</span>{' '}
          <span className="font-mono text-neutral-400">
            {(hoveredSegment.start_ms / 1000).toFixed(2)}s - {(hoveredSegment.end_ms / 1000).toFixed(2)}s
          </span>
          <p className="text-[11px] text-neutral-300 truncate mt-0.5">{hoveredSegment.translated}</p>
        </div>
      )}
    </div>
  );
};
