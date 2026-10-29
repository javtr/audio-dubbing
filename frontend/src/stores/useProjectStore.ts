import { create } from 'zustand';
import { ProjectPaths, ReferenceItem, Segment, ValidationResult } from '../types';
import * as api from '../api/client';

interface ProjectState {
  projectsList: string[];
  currentProject: string | null;
  language: string;
  paths: ProjectPaths | null;
  audioDurationMs: number;
  segments: Segment[];
  validation: ValidationResult | null;
  transcript: string;

  activeTab: 'script' | 'dubbing' | 'studio';
  selectedSegmentId: string | null;

  isTTSConnected: boolean;
  ttsUrl: string;
  references: ReferenceItem[];

  liveStatusMessage: string;
  liveProgress: { current: number; total: number; percent: number } | null;
  isBatchGenerating: boolean;
  isNewProjectModalOpen: boolean;

  // Actions
  setActiveTab: (tab: 'script' | 'dubbing' | 'studio') => void;
  setSelectedSegmentId: (id: string | null) => void;
  setLiveStatus: (msg: string) => void;
  setTranscript: (t: string) => void;
  setIsNewProjectModalOpen: (open: boolean) => void;
  loadProjectsList: () => Promise<void>;
  selectProject: (name: string) => Promise<void>;
  closeProject: () => void;
  setSegments: (segments: Segment[]) => void;
  updateSegment: (id: string | number, patch: Partial<Segment>) => void;
  saveCurrentMetadata: () => Promise<void>;
  revertToMaster: () => Promise<void>;
  reloadProject: () => Promise<void>;
  checkTTS: () => Promise<void>;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectsList: [],
  currentProject: null,
  language: 'en',
  paths: null,
  audioDurationMs: 0,
  segments: [],
  validation: null,
  transcript: '',

  activeTab: 'script',
  selectedSegmentId: null,

  isTTSConnected: false,
  ttsUrl: '',
  references: [],

  liveStatusMessage: '',
  liveProgress: null,
  isBatchGenerating: false,
  isNewProjectModalOpen: false,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setSelectedSegmentId: (id) => set({ selectedSegmentId: id }),
  setLiveStatus: (msg) => set({ liveStatusMessage: msg }),
  setTranscript: (t) => set({ transcript: t }),
  setIsNewProjectModalOpen: (open) => set({ isNewProjectModalOpen: open }),

  loadProjectsList: async () => {
    try {
      const list = await api.getProjects();
      set({ projectsList: list });
      // No cargar ningún proyecto automáticamente en el inicio para evitar demoras
    } catch (e) {
      console.error('Error loading projects list', e);
    }
  },

  closeProject: () => {
    set({
      currentProject: null,
      language: 'en',
      paths: null,
      audioDurationMs: 0,
      segments: [],
      validation: null,
      transcript: '',
      selectedSegmentId: null,
      references: [],
      liveStatusMessage: '',
      liveProgress: null,
    });
  },

  selectProject: async (name: string) => {
    if (!name) {
      get().closeProject();
      return;
    }
    try {
      const detail = await api.getProjectDetail(name);
      set({
        currentProject: detail.name,
        language: detail.language,
        paths: detail.paths,
        audioDurationMs: detail.audio_duration_ms,
        segments: detail.metadata,
        validation: detail.validation,
        transcript: detail.transcript || '',
        selectedSegmentId: detail.metadata.length > 0 ? String(detail.metadata[0].id) : null,
      });

      const refs = await api.getTTSReferences(detail.language);
      set({ references: refs });
    } catch (e) {
      console.error(`Error selecting project ${name}`, e);
    }
  },

  setSegments: (segments: Segment[]) => set({ segments }),

  updateSegment: (id: string | number, patch: Partial<Segment>) => {
    const updated = get().segments.map((seg) => {
      if (String(seg.id) === String(id)) {
        return { ...seg, ...patch };
      }
      return seg;
    });
    set({ segments: updated });
  },

  saveCurrentMetadata: async () => {
    const { currentProject, segments } = get();
    if (!currentProject) return;
    try {
      const val = await api.saveProjectMetadata(currentProject, segments);
      set({ validation: val });
    } catch (e) {
      console.error('Error saving metadata', e);
    }
  },

  revertToMaster: async () => {
    const { currentProject } = get();
    if (!currentProject) return;
    try {
      const master = await api.resetToMaster(currentProject);
      set({ segments: master });
    } catch (e) {
      console.error('Error reverting to master', e);
    }
  },

  reloadProject: async () => {
    const { currentProject } = get();
    if (!currentProject) return;
    try {
      await get().selectProject(currentProject);
    } catch (e) {
      console.error('Error reloading project', e);
    }
  },

  checkTTS: async () => {
    const status = await api.checkTTSStatus();
    set({ isTTSConnected: status.connected, ttsUrl: status.url });
  },
}));

