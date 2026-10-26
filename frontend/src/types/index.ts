export interface Segment {
  id: string | number;
  start_ms: number;
  end_ms: number;
  orig_start_ms?: number;
  orig_end_ms?: number;
  original: string;
  translated: string;
  filename: string;
  clip_duration_ms?: number;
  raw_duration_ms?: number;
  speed_ratio?: number;
  is_manual_ratio?: boolean;
  current_speed_ratio?: number;
}

export interface SilenceGap {
  start_ms: number;
  end_ms: number;
  dur_s: number;
  segment_id: string;
  level: 'warning' | 'critical';
}

export interface AllWaveformsResponse {
  duration_ms: number;
  orig_peaks: number[];
  dub_peaks: number[];
  silences: SilenceGap[];
}

export interface ValidationResult {
  has_errors: boolean;
  error_count: number;
  total_count: number;
  summary_text: string;
  anomalies: Record<string, string[]>;
}

export interface ProjectPaths {
  project_dir: string;
  audio_file: string;
  video_file: string;
  audios_dir: string;
  mix_dir: string;
  metadata_file: string;
  master_metadata_file: string;
}

export interface ProjectDetail {
  name: string;
  language: string;
  paths: ProjectPaths;
  audio_duration_ms: number;
  metadata: Segment[];
  validation: ValidationResult;
  transcript?: string;
}

export interface ReferenceItem {
  segmento: string;
  transcripcion: string;
  tono: string;
  exists: boolean;
  audio_url: string;
}
