import axios from 'axios';
import { ProjectDetail, ReferenceItem, Segment, ValidationResult } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getProjects = async (): Promise<string[]> => {
  const res = await api.get('/projects');
  return res.data.projects;
};

export const getProjectDetail = async (name: string): Promise<ProjectDetail> => {
  const res = await api.get(`/projects/${name}`);
  return res.data;
};

export const createProject = async (name: string, mediaPath: string, language = 'en') => {
  const res = await api.post('/projects', { name, media_path: mediaPath, language });
  return res.data;
};

export const saveProjectMetadata = async (name: string, metadata: Segment[]): Promise<ValidationResult> => {
  const res = await api.post(`/projects/${name}/metadata`, { metadata });
  return res.data.validation;
};

export const resetToMaster = async (name: string): Promise<Segment[]> => {
  const res = await api.post(`/projects/${name}/reset-master`);
  return res.data.metadata;
};

export const transcribeAudio = async (project: string) => {
  const res = await api.post('/script/transcribe', { project });
  return res.data;
};

export const generateGeminiPrompt = async (project: string, transcript: string) => {
  const res = await api.post('/script/generate-prompt', { project, transcript });
  return res.data;
};

export const alignScript = async (project: string, geminiData: Segment[], splitOnPauses = true) => {
  const res = await api.post('/script/align', {
    project,
    gemini_data: geminiData,
    split_on_pauses: splitOnPauses,
  });
  return res.data;
};

export const checkTTSStatus = async (): Promise<{ connected: boolean; url: string }> => {
  try {
    const res = await api.get('/tts/status');
    return res.data;
  } catch {
    return { connected: false, url: '' };
  }
};

export const getTTSReferences = async (language = 'en'): Promise<ReferenceItem[]> => {
  const res = await api.get(`/tts/references?language=${language}`);
  return res.data.references;
};

export const generateSingleTTS = async (project: string, segmentId: string | number, refName: string) => {
  const res = await api.post('/tts/generate-single', {
    project,
    segment_id: String(segmentId),
    ref_name: refName,
  });
  return res.data;
};

export const generateBatchTTS = async (project: string, segmentIds: (string | number)[], defaultRef: string) => {
  const res = await api.post('/tts/generate-batch', {
    project,
    segment_ids: segmentIds.map(String),
    default_ref: defaultRef,
  });
  return res.data;
};

export const stopTTS = async () => {
  const res = await api.post('/tts/stop');
  return res.data;
};

export const autoSplitSegment = async (project: string, segmentId: string | number) => {
  const res = await api.post('/timeline/auto-split', {
    project,
    segment_id: String(segmentId),
  });
  return res.data;
};

export const autoSplitAllSegments = async (project: string) => {
  const res = await api.post('/timeline/auto-split-all', { project });
  return res.data;
};

export const exportProject = async (
  project: string,
  outputPath: string,
  exportType: 'video' | 'audio',
  volOrig = 1.0,
  muteOrig = false,
  volDub = 1.0,
  muteDub = false
) => {
  const res = await api.post('/export', {
    project,
    export_type: exportType,
    output_path: outputPath,
    vol_orig: volOrig,
    mute_orig: muteOrig,
    vol_dub: volDub,
    mute_dub: muteDub,
  });
  return res.data;
};

export const getOriginalWaveform = async (project: string, points = 1500) => {
  const res = await api.get(`/waveform/${project}/original?points=${points}`);
  return res.data;
};


export const getAllWaveforms = async (project: string, points = 1600): Promise<import('../types').AllWaveformsResponse> => {
  const res = await api.get(`/waveform/${project}/all?points=${points}`);
  return res.data;
};

export const adjustSegmentRatio = async (
  project: string,
  segmentId: string | number,
  ratio: number,
  startMs?: number
) => {
  const res = await api.post('/timeline/adjust-ratio', {
    project,
    segment_id: String(segmentId),
    ratio: Number(ratio),
    start_ms: startMs !== undefined ? Number(startMs) : undefined,
  });
  return res.data;
};

export const resetRawAudios = async (
  project: string,
  segmentId?: string | number
): Promise<{ status: string; restored_count: number; metadata: import('../types').Segment[]; validation: any }> => {
  const res = await api.post('/timeline/reset-raw-audios', {
    project,
    segment_id: segmentId ? String(segmentId) : null,
  });
  return res.data;
};

export const updateProjectTimings = async (
  project: string,
  timings: { id: string | number; start_ms: number }[]
) => {
  const res = await api.post('/timeline/update-timings', {
    project,
    timings: timings.map((t) => ({ id: String(t.id), start_ms: Number(t.start_ms) })),
  });
  return res.data;
};

export const deleteSegment = async (project: string, segmentId: string | number) => {
  const res = await api.post('/timeline/delete-segment', {
    project,
    segment_id: String(segmentId),
  });
  return res.data;
};

export const generateRetranslationPrompt = async (project: string) => {
  const res = await api.post('/script/generate-retranslation-prompt', { project });
  return res.data;
};

export const applyRetranslation = async (project: string, retranslatedJson: any[]) => {
  const res = await api.post('/script/apply-retranslation', {
    project,
    retranslated_json: retranslatedJson,
  });
  return res.data;
};

export const applyManualChanges = async (
  project: string,
  changes: { id: string | number; start_ms: number; ratio: number }[]
) => {
  const res = await api.post('/timeline/apply-manual-changes', {
    project,
    changes: changes.map((c) => ({
      id: String(c.id),
      start_ms: Number(c.start_ms),
      ratio: Number(c.ratio),
    })),
  });
  return res.data;
};

export const autoCalculateRatios = async (project: string) => {
  const res = await api.post('/timeline/auto-ratios', { project });
  return res.data;
};
