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

  // Initialize Audio Elements & AudioContext
  useEffect(() => {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    audioCtxRef.current = ctx;

    const origEl = new Audio();
    const dubEl = new Audio();
    origEl.preload = 'auto';
    dubEl.preload = 'auto';

    origAudioRef.current = origEl;
    dubAudioRef.current = dubEl;

    try {
      const origSource = ctx.createMediaElementSource(origEl);
      const origGain = ctx.createGain();
      origSource.connect(origGain).connect(ctx.destination);
      origGainRef.current = origGain;
    } catch (e) {
      console.warn('Original MediaElementSource fallback', e);
    }

    try {
      const dubSource = ctx.createMediaElementSource(dubEl);
      const dubGain = ctx.createGain();
      dubSource.connect(dubGain).connect(ctx.destination);
      dubGainRef.current = dubGain;
    } catch (e) {
      console.warn('Dubbed MediaElementSource fallback', e);
    }

    return () => {
      origEl.pause();
      dubEl.pause();
      ctx.close();
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
      dubAudioRef.current.src = dubbedMixUrl;
      dubAudioRef.current.load();
    }
  }, [dubbedMixUrl]);

  // Volume & Mute updates (Supports 0.0 to 2.0 via GainNode)
  useEffect(() => {
    const targetVol = isMuteOrig ? 0 : volOrig;
    if (origGainRef.current) {
      origGainRef.current.gain.value = targetVol;
    } else if (origAudioRef.current) {
      origAudioRef.current.volume = Math.min(1.0, targetVol);
    }
  }, [volOrig, isMuteOrig]);

  useEffect(() => {
    const targetVol = isMuteDub ? 0 : volDub;
    if (dubGainRef.current) {
      dubGainRef.current.gain.value = targetVol;
    } else if (dubAudioRef.current) {
      dubAudioRef.current.volume = Math.min(1.0, targetVol);
    }
  }, [volDub, isMuteDub]);

  // Time tracking loop
  useEffect(() => {
    let animId: number;

    const updateTime = () => {
      if (origAudioRef.current && isPlaying) {
        setCurrentTimeMs(Math.round(origAudioRef.current.currentTime * 1000));
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
      audioCtxRef.current.resume();
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
