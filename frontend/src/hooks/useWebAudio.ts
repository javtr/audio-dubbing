import { useRef, useState, useEffect, useCallback } from 'react';

export function useWebAudio(originalUrl?: string, dubbedMixUrl?: string) {
  const audioCtxRef = useRef<AudioContext | null>(null);

  const origAudioRef = useRef<HTMLAudioElement | null>(null);
  const dubAudioRef = useRef<HTMLAudioElement | null>(null);

  const origGainRef = useRef<GainNode | null>(null);
  const dubGainRef = useRef<GainNode | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);

  const [volOrig, setVolOrig] = useState(1.0);
  const [volDub, setVolDub] = useState(1.0);
  const [isMuteOrig, setIsMuteOrig] = useState(false);
  const [isMuteDub, setIsMuteDub] = useState(false);

  // Initialize Audio Elements & Web Audio Nodes
  useEffect(() => {
    let ctx: AudioContext | null = null;
    try {
      ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioCtxRef.current = ctx;
    } catch (e) {
      console.warn('Web Audio Context not supported', e);
    }

    const origEl = new Audio();
    const dubEl = new Audio();
    origEl.preload = 'auto';
    dubEl.preload = 'auto';
    origEl.crossOrigin = 'anonymous';
    dubEl.crossOrigin = 'anonymous';

    origAudioRef.current = origEl;
    dubAudioRef.current = dubEl;

    if (ctx) {
      try {
        const origSource = ctx.createMediaElementSource(origEl);
        const origGain = ctx.createGain();
        origSource.connect(origGain).connect(ctx.destination);
        origGainRef.current = origGain;
      } catch (e) {
        console.warn('Original MediaElementSource fallback to direct element', e);
      }

      try {
        const dubSource = ctx.createMediaElementSource(dubEl);
        const dubGain = ctx.createGain();
        dubSource.connect(dubGain).connect(ctx.destination);
        dubGainRef.current = dubGain;
      } catch (e) {
        console.warn('Dubbed MediaElementSource fallback to direct element', e);
      }
    }

    origEl.onended = () => {
      setIsPlaying(false);
      dubEl.pause();
    };

    return () => {
      origEl.pause();
      dubEl.pause();
      if (ctx && ctx.state !== 'closed') {
        try {
          ctx.close();
        } catch (_) {}
      }
    };
  }, []);

  // Update source URLs
  useEffect(() => {
    if (origAudioRef.current && originalUrl) {
      origAudioRef.current.src = originalUrl;
      origAudioRef.current.load();
    }
  }, [originalUrl]);

  useEffect(() => {
    if (dubAudioRef.current && dubbedMixUrl) {
      const wasPlaying = isPlaying;
      const curSec = currentTimeMs / 1000;
      dubAudioRef.current.src = dubbedMixUrl;
      dubAudioRef.current.load();
      if (wasPlaying) {
        dubAudioRef.current.currentTime = curSec;
        dubAudioRef.current.play().catch(() => {});
      }
    }
  }, [dubbedMixUrl]);

  // Real-time Volume & Mute updates (Direct HTML5 Audio + WebAudio Gain boost)
  useEffect(() => {
    const isMuted = isMuteOrig || volOrig === 0;
    const clampedVol = Math.max(0, Math.min(1.0, volOrig));

    if (origAudioRef.current) {
      origAudioRef.current.muted = isMuted;
      origAudioRef.current.volume = isMuted ? 0 : clampedVol;
    }

    if (origGainRef.current) {
      try {
        origGainRef.current.gain.value = isMuted ? 0 : volOrig;
      } catch (e) {
        // GainNode fallback
      }
    }
  }, [volOrig, isMuteOrig]);

  useEffect(() => {
    const isMuted = isMuteDub || volDub === 0;
    const clampedVol = Math.max(0, Math.min(1.0, volDub));

    if (dubAudioRef.current) {
      dubAudioRef.current.muted = isMuted;
      dubAudioRef.current.volume = isMuted ? 0 : clampedVol;
    }

    if (dubGainRef.current) {
      try {
        dubGainRef.current.gain.value = isMuted ? 0 : volDub;
      } catch (e) {
        // GainNode fallback
      }
    }
  }, [volDub, isMuteDub]);

  // Precise Time tracking loop with cross-track drift synchronization
  useEffect(() => {
    let animId: number;

    const updateTime = () => {
      if (origAudioRef.current && isPlaying) {
        const curSec = origAudioRef.current.currentTime;
        setCurrentTimeMs(Math.round(curSec * 1000));

        // Lock dubbed track to original track if drift exceeds 120ms
        if (
          dubAudioRef.current &&
          !dubAudioRef.current.paused &&
          dubAudioRef.current.readyState >= 2
        ) {
          const drift = Math.abs(dubAudioRef.current.currentTime - curSec);
          if (drift > 0.12) {
            dubAudioRef.current.currentTime = curSec;
          }
        }

        animId = requestAnimationFrame(updateTime);
      }
    };

    if (isPlaying) {
      animId = requestAnimationFrame(updateTime);
    }

    return () => cancelAnimationFrame(animId);
  }, [isPlaying]);

  const play = useCallback(() => {
    if (audioCtxRef.current && audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume().catch(() => {});
    }

    const curSec = currentTimeMs / 1000;

    if (origAudioRef.current && origAudioRef.current.src) {
      origAudioRef.current.currentTime = curSec;
      origAudioRef.current.play().catch((e) => console.warn('Orig audio play error:', e));
    }

    if (dubAudioRef.current && dubAudioRef.current.src) {
      dubAudioRef.current.currentTime = curSec;
      dubAudioRef.current.play().catch((e) => console.warn('Dub audio play error:', e));
    }

    setIsPlaying(true);
  }, [currentTimeMs]);

  const pause = useCallback(() => {
    origAudioRef.current?.pause();
    dubAudioRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const seek = useCallback((timeMs: number) => {
    const sec = timeMs / 1000;
    if (origAudioRef.current) {
      origAudioRef.current.currentTime = sec;
    }
    if (dubAudioRef.current) {
      dubAudioRef.current.currentTime = sec;
    }
    setCurrentTimeMs(timeMs);
  }, []);

  const stop = useCallback(() => {
    pause();
    seek(0);
  }, [pause, seek]);

  return {
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
  };
}
