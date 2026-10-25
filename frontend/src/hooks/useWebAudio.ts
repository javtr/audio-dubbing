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
    origAudioRef.current = origEl;
    dubAudioRef.current = dubEl;

    try {
      const origSource = ctx.createMediaElementSource(origEl);
      const origGain = ctx.createGain();
      origSource.connect(origGain).connect(ctx.destination);
      origGainRef.current = origGain;

      const dubSource = ctx.createMediaElementSource(dubEl);
      const dubGain = ctx.createGain();
      dubSource.connect(dubGain).connect(ctx.destination);
      dubGainRef.current = dubGain;
    } catch {
      // Fallback direct connection
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
    }
  }, [originalUrl]);

  useEffect(() => {
    if (dubAudioRef.current && dubbedMixUrl) {
      dubAudioRef.current.src = dubbedMixUrl;
    }
  }, [dubbedMixUrl]);

  // Volume & Mute updates
  useEffect(() => {
    if (origGainRef.current) {
      origGainRef.current.gain.value = isMuteOrig ? 0 : volOrig;
    }
    if (origAudioRef.current) {
      origAudioRef.current.volume = isMuteOrig ? 0 : Math.min(1.0, volOrig);
    }
  }, [volOrig, isMuteOrig]);

  useEffect(() => {
    if (dubGainRef.current) {
      dubGainRef.current.gain.value = isMuteDub ? 0 : volDub;
    }
    if (dubAudioRef.current) {
      dubAudioRef.current.volume = isMuteDub ? 0 : Math.min(1.0, volDub);
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
    if (audioCtxRef.current?.state === 'suspended') {
      audioCtxRef.current.resume();
    }
    if (origAudioRef.current) {
      origAudioRef.current.play().catch(() => {});
    }
    if (dubAudioRef.current && dubAudioRef.current.src) {
      dubAudioRef.current.currentTime = origAudioRef.current ? origAudioRef.current.currentTime : 0;
      dubAudioRef.current.play().catch(() => {});
    }
    setIsPlaying(true);
  }, []);

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

