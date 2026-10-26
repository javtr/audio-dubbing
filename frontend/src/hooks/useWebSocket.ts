import { useEffect, useRef } from 'react';
import { useProjectStore } from '../stores/useProjectStore';

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/progress`;

    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const store = useProjectStore.getState();

          switch (data.type) {
            case 'transcribe_status':
            case 'align_status':
            case 'export_status':
              store.setLiveStatus(data.status || '');
              break;

            case 'transcribe_complete':
              if (data.text) store.setTranscript(data.text);
              store.setLiveStatus('¡Transcripción completada con éxito!');
              break;

            case 'transcribe_and_segment_complete':
              store.setSegments(data.segments);
              if (data.transcript) store.setTranscript(data.transcript);
              store.setLiveStatus(`¡Audio transcrito y dividido en ${data.segments.length} secciones acústicas con éxito!`);
              break;

            case 'align_complete':
              store.setSegments(data.segments);
              store.setLiveStatus(`¡Sincronización finalizada! ${data.segments.length} segmentos alineados.`);
              break;

            case 'tts_progress':
              useProjectStore.setState({
                isBatchGenerating: true,
                liveStatusMessage: data.status,
                liveProgress: {
                  current: data.current,
                  total: data.total,
                  percent: Math.round((data.current / data.total) * 100),
                },
              });
              break;

            case 'tts_segment_done':
              store.updateSegment(data.segment_id, {
                clip_duration_ms: data.clip_duration_ms,
                current_speed_ratio: data.speed_ratio,
              });
              break;

            case 'tts_batch_complete':
            case 'tts_batch_stopped':
              useProjectStore.setState({
                isBatchGenerating: false,
                liveProgress: null,
                liveStatusMessage: data.type === 'tts_batch_complete' ? '¡Doblaje completado!' : 'Generación detenida.',
              });
              break;

            case 'export_complete':
              store.setLiveStatus(`¡Exportación exitosa! Guardado en: ${data.output_path}`);
              break;

            case 'transcribe_error':
            case 'align_error':
            case 'export_error':
            case 'tts_segment_error':
              store.setLiveStatus(`Error: ${data.error}`);
              break;
          }
        } catch (e) {
          console.error('Error handling WebSocket message', e);
        }
      };

      ws.onclose = () => {
        // Reconnect after 2 seconds
        setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      wsRef.current?.close();
    };
  }, []);

  return wsRef;
}

