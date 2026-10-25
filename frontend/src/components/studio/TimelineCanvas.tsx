import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Segment } from '../../types';

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
  origWaveformPoints?: number[];
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
  origWaveformPoints = [],
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredSegment, setHoveredSegment] = useState<Segment | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ x: number; offset: number }>({ x: 0, offset: 0 });

  const TRACK1_Y = 30;
  const TRACK1_H = 75;
  const TRACK2_Y = 120;
  const TRACK2_H = 75;
  const TOTAL_H = 210;

  // Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Helper: ms to canvas X
    const msToX = (ms: number) => ((ms - viewOffsetMs) / 1000) * zoom;
    const xToMs = (x: number) => viewOffsetMs + (x / zoom) * 1000;

    // Clear background
    ctx.fillStyle = '#121212';
    ctx.fillRect(0, 0, width, height);

    // 1. Time Ruler & Grid
    ctx.fillStyle = '#1e1e1e';
    ctx.fillRect(0, 0, width, 24);
    ctx.strokeStyle = '#2a2a2a';
    ctx.lineWidth = 1;

    // Second markers
    const secStep = zoom > 100 ? 1 : zoom > 40 ? 5 : 10;
    const startSec = Math.floor(viewOffsetMs / 1000);
    const endSec = Math.ceil(xToMs(width) / 1000);

    ctx.fillStyle = '#737373';
    ctx.font = '10px monospace';
    for (let s = startSec; s <= endSec; s += secStep) {
      const x = msToX(s * 1000);
      if (x >= 0 && x <= width) {
        ctx.beginPath();
        ctx.moveTo(x, 14);
        ctx.lineTo(x, 24);
        ctx.stroke();

        const mins = Math.floor(s / 60);
        const secs = s % 60;
        const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        ctx.fillText(timeStr, x + 4, 18);
      }
    }

    // 2. Track 1: Original Audio Track Background
    ctx.fillStyle = '#171717';
    ctx.fillRect(0, TRACK1_Y, width, TRACK1_H);
    ctx.strokeStyle = '#262626';
    ctx.strokeRect(0, TRACK1_Y, width, TRACK1_H);

    // Track 1 Waveform
    if (origWaveformPoints.length > 0 && totalDurationMs > 0) {
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      const midY = TRACK1_Y + TRACK1_H / 2;
      const ptsCount = origWaveformPoints.length;

      for (let i = 0; i < ptsCount; i++) {
        const pointMs = (i / ptsCount) * totalDurationMs;
        const x = msToX(pointMs);
        if (x >= 0 && x <= width) {
          const val = origWaveformPoints[i];
          const y = midY - val * (TRACK1_H * 0.42);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    // Track 1 Header Tag
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(8, TRACK1_Y + 4, 110, 18);
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 10px sans-serif';
    ctx.fillText('Pista Original (ES)', 14, TRACK1_Y + 16);

    // 3. Track 2: Dubbed Audio Track Background
    ctx.fillStyle = '#171717';
    ctx.fillRect(0, TRACK2_Y, width, TRACK2_H);
    ctx.strokeStyle = '#262626';
    ctx.strokeRect(0, TRACK2_Y, width, TRACK2_H);

    // Track 2 Header Tag
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(8, TRACK2_Y + 4, 115, 18);
    ctx.fillStyle = '#22c55e';
    ctx.font = 'bold 10px sans-serif';
    ctx.fillText('Pista Doblada (TTS)', 14, TRACK2_Y + 16);

    // Draw Segments in Track 2
    segments.forEach((seg) => {
      const x1 = msToX(seg.start_ms);
      const x2 = msToX(seg.end_ms);
      if (x2 < 0 || x1 > width) return; // Frustum culling

      const blockW = Math.max(3, x2 - x1);
      const isSelected = selectedSegmentId === String(seg.id);
      const ratio = seg.current_speed_ratio || 1.0;
      const hasAudio = seg.clip_duration_ms && seg.clip_duration_ms > 0;

      // Color coding based on speed
      let fillColor = 'rgba(34, 197, 94, 0.25)'; // Green 1.0x
      let strokeColor = '#22c55e';
      if (ratio > 1.35) {
        fillColor = 'rgba(239, 68, 68, 0.35)'; // Red
        strokeColor = '#ef4444';
      } else if (ratio > 1.20 || ratio < 0.90) {
        fillColor = 'rgba(245, 158, 11, 0.3)'; // Amber
        strokeColor = '#f59e0b';
      }

      if (!hasAudio) {
        fillColor = 'rgba(64, 64, 64, 0.25)';
        strokeColor = '#525252';
      }

      if (isSelected) {
        ctx.fillStyle = 'rgba(56, 189, 248, 0.35)';
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2;
      } else {
        ctx.fillStyle = fillColor;
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1;
      }

      ctx.fillRect(x1, TRACK2_Y + 4, blockW, TRACK2_H - 8);
      ctx.strokeRect(x1, TRACK2_Y + 4, blockW, TRACK2_H - 8);

      // Segment text snippet
      if (blockW > 35) {
        ctx.fillStyle = '#ffffff';
        ctx.font = '10px sans-serif';
        const label = `[${seg.id}] ${ratio.toFixed(2)}x`;
        ctx.fillText(label, x1 + 4, TRACK2_Y + 22);

        if (blockW > 70) {
          ctx.fillStyle = '#a3a3a3';
          ctx.font = '9px sans-serif';
          const textPreview = seg.translated.slice(0, Math.floor(blockW / 7));
          ctx.fillText(textPreview, x1 + 4, TRACK2_Y + 38);
        }
      }
    });

    // 4. Playhead (Scrubber Line)
    const playheadX = msToX(playheadMs);
    if (playheadX >= 0 && playheadX <= width) {
      // Glow effect
      ctx.strokeStyle = 'rgba(249, 115, 22, 0.3)';
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(playheadX, 0);
      ctx.lineTo(playheadX, height);
      ctx.stroke();

      // Sharp line
      ctx.strokeStyle = '#f97316';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(playheadX, 0);
      ctx.lineTo(playheadX, height);
      ctx.stroke();

      // Playhead Top Handle
      ctx.fillStyle = '#f97316';
      ctx.beginPath();
      ctx.moveTo(playheadX - 6, 0);
      ctx.lineTo(playheadX + 6, 0);
      ctx.lineTo(playheadX, 10);
      ctx.closePath();
      ctx.fill();
    }
  }, [segments, totalDurationMs, playheadMs, zoom, viewOffsetMs, selectedSegmentId, origWaveformPoints]);

  // Handle click / seek / split
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const clickedMs = viewOffsetMs + (x / zoom) * 1000;

    // Check if middle click or Alt-drag for pan
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
      // Select segment if clicked inside Track 2
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
    const x = e.clientX - rect.left;
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
        width={1400}
        height={TOTAL_H}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className={`w-full rounded-xl bg-neutral-900 border border-neutral-800 ${
          activeTool === 'razor' ? 'cursor-crosshair' : 'cursor-pointer'
        }`}
      />

      {/* Hover Tooltip */}
      {hoveredSegment && (
        <div className="absolute top-2 right-4 bg-neutral-950/90 border border-neutral-700 rounded-lg px-3 py-1.5 text-xs text-neutral-200 pointer-events-none shadow-xl max-w-sm">
          <span className="font-bold text-sky-400">[{hoveredSegment.id}]</span>{' '}
          <span className="font-mono text-neutral-400">
            {(hoveredSegment.start_ms / 1000).toFixed(1)}s - {(hoveredSegment.end_ms / 1000).toFixed(1)}s
          </span>
          <p className="text-[11px] text-neutral-300 truncate mt-0.5">{hoveredSegment.original}</p>
        </div>
      )}
    </div>
  );
};
