import { Segment } from '../types';

export interface CollisionRegion {
  segIdA: string;
  segIdB: string;
  startMs: number;
  endMs: number;
  overlapMs: number;
}

export interface SegmentCollisionInfo {
  outgoing: { otherId: string; overlapMs: number }[];
  incoming: { otherId: string; overlapMs: number }[];
  maxOverlapMs: number;
}

export interface OverlapAnalysisResult {
  hasOverlaps: boolean;
  totalOverlaps: number;
  collisionRegions: CollisionRegion[];
  segmentCollisions: Record<string, SegmentCollisionInfo>;
}

/**
 * Calcula el tiempo de fin efectivo del audio para un segmento, considerando
 * posibles cambios locales de inicio (start_ms) y de ratio de velocidad antes de aplicar.
 */
export function calculateEffectiveEnd(
  seg: Segment,
  localStarts: Record<string, number> = {},
  localRatios: Record<string, number> = {}
): number {
  const sid = String(seg.id);
  const startMs = localStarts[sid] !== undefined ? localStarts[sid] : seg.start_ms;
  const ratio = localRatios[sid] !== undefined ? localRatios[sid] : (seg.speed_ratio ?? seg.current_speed_ratio ?? 1.0);

  let durationMs = 0;
  if (seg.clip_duration_ms && seg.clip_duration_ms > 0) {
    const activeRatio = seg.current_speed_ratio || 1.0;
    // Duración virgen 1.0x derivada
    const rawDur = seg.raw_duration_ms || (seg.clip_duration_ms * activeRatio);
    // Duración resultante con el ratio objetivo
    durationMs = rawDur / Math.max(0.1, ratio);
  } else {
    durationMs = Math.max(100, seg.end_ms - seg.start_ms);
  }

  return startMs + durationMs;
}

/**
 * Analiza la lista de segmentos y detecta cualquier colisión o traslape entre audios consecutivos o encimados.
 */
export function detectOverlaps(
  segments: Segment[],
  localStarts: Record<string, number> = {},
  localRatios: Record<string, number> = {}
): OverlapAnalysisResult {
  if (!segments || segments.length < 2) {
    return {
      hasOverlaps: false,
      totalOverlaps: 0,
      collisionRegions: [],
      segmentCollisions: {},
    };
  }

  // Ordenar segmentos cronológicamente por su inicio efectivo
  const sorted = [...segments].sort((a, b) => {
    const sA = localStarts[String(a.id)] !== undefined ? localStarts[String(a.id)] : a.start_ms;
    const sB = localStarts[String(b.id)] !== undefined ? localStarts[String(b.id)] : b.start_ms;
    return sA - sB;
  });

  const collisionRegions: CollisionRegion[] = [];
  const segmentCollisions: Record<string, SegmentCollisionInfo> = {};

  const getOrInitInfo = (id: string): SegmentCollisionInfo => {
    if (!segmentCollisions[id]) {
      segmentCollisions[id] = {
        outgoing: [],
        incoming: [],
        maxOverlapMs: 0,
      };
    }
    return segmentCollisions[id];
  };

  for (let i = 0; i < sorted.length - 1; i++) {
    const cur = sorted[i];
    const curId = String(cur.id);
    const curStart = localStarts[curId] !== undefined ? localStarts[curId] : cur.start_ms;
    const curEnd = calculateEffectiveEnd(cur, localStarts, localRatios);

    for (let j = i + 1; j < sorted.length; j++) {
      const next = sorted[j];
      const nextId = String(next.id);
      const nextStart = localStarts[nextId] !== undefined ? localStarts[nextId] : next.start_ms;
      const nextEnd = calculateEffectiveEnd(next, localStarts, localRatios);

      // Tolerancia de 15ms para ignorar micro-redondeos de coma flotante
      if (nextStart >= curEnd - 15) {
        break;
      }

      // Existe colisión real entre cur y next
      const overlapStart = nextStart;
      const overlapEnd = Math.min(curEnd, nextEnd);
      const overlapMs = curEnd - nextStart;

      if (overlapMs > 15) {
        collisionRegions.push({
          segIdA: curId,
          segIdB: nextId,
          startMs: overlapStart,
          endMs: overlapEnd,
          overlapMs,
        });

        const curInfo = getOrInitInfo(curId);
        curInfo.outgoing.push({ otherId: nextId, overlapMs });
        curInfo.maxOverlapMs = Math.max(curInfo.maxOverlapMs, overlapMs);

        const nextInfo = getOrInitInfo(nextId);
        nextInfo.incoming.push({ otherId: curId, overlapMs });
        nextInfo.maxOverlapMs = Math.max(nextInfo.maxOverlapMs, overlapMs);
      }
    }
  }

  return {
    hasOverlaps: collisionRegions.length > 0,
    totalOverlaps: collisionRegions.length,
    collisionRegions,
    segmentCollisions,
  };
}
