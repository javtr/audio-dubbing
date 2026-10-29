import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useProjectStore } from '../stores/useProjectStore';
import { Folder, Plus, Radio, RefreshCw, Sparkles, CheckCircle2, AlertTriangle } from 'lucide-react';
import * as api from '../api/client';

export const Navbar: React.FC = () => {
  const {
    projectsList,
    currentProject,
    language,
    activeTab,
    isTTSConnected,
    isTTSLoaded,
    isTTSToggling,
    ttsUrl,
    isNewProjectModalOpen,
    setActiveTab,
    selectProject,
    closeProject,
    setIsNewProjectModalOpen,
    loadProjectsList,
    checkTTS,
    toggleTTSModel,
  } = useProjectStore();
  const [newProjectName, setNewProjectName] = useState('');
  const [newMediaPath, setNewMediaPath] = useState('');
  const [newLang, setNewLang] = useState('en');
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async () => {
    if (!newProjectName.trim() || !newMediaPath.trim()) return;
    setIsCreating(true);
    try {
      await api.createProject(newProjectName.trim(), newMediaPath.trim(), newLang);
      await loadProjectsList();
      await selectProject(newProjectName.trim());
      setIsNewProjectModalOpen(false);
      setNewProjectName('');
      setNewMediaPath('');
    } catch (err: any) {
      alert(`Error al crear proyecto: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <header className="border-b border-neutral-800 bg-neutral-900/90 backdrop-blur sticky top-0 z-50 shrink-0">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
        {/* Left: Brand & Project Selector */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-sky-500/20 border border-sky-500/40 flex items-center justify-center text-sky-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <span className="font-bold text-base tracking-tight bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent">
              Audio Dubbing Studio
            </span>
          </div>

          <div className="h-6 w-px bg-neutral-800" />

          {/* Project dropdown */}
          <div className="flex items-center gap-2 bg-neutral-800/80 border border-neutral-700/60 rounded-lg px-2.5 py-1">
            <Folder className="w-4 h-4 text-neutral-400" />
            <select
              value={currentProject || ''}
              onChange={(e) => {
                const val = e.target.value;
                if (val === '__close__') {
                  closeProject();
                } else if (val) {
                  selectProject(val);
                }
              }}
              className="bg-transparent text-sm font-medium text-neutral-200 outline-none cursor-pointer max-w-[210px] truncate"
            >
              <option value="" disabled className="bg-neutral-900 text-neutral-400">
                Seleccionar proyecto...
              </option>
              {projectsList.map((p) => (
                <option key={p} value={p} className="bg-neutral-900 text-neutral-200">
                  {p}
                </option>
              ))}
              {currentProject && (
                <option value="__close__" className="bg-neutral-900 text-rose-400 font-semibold">
                  ✕ Cerrar proyecto
                </option>
              )}
            </select>
          </div>

          <button
            onClick={() => setIsNewProjectModalOpen(true)}
            className="p-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-300 hover:text-white transition flex items-center gap-1 text-xs font-semibold px-2"
            title="Crear nuevo proyecto"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Nuevo</span>
          </button>
        </div>

        {/* Center: Tabs Navigation */}
        <nav className="flex items-center gap-1 bg-neutral-950 p-1 rounded-xl border border-neutral-800">
          <button
            onClick={() => setActiveTab('script')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === 'script'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
            }`}
          >
            Paso 1: Guion y Tiempos
          </button>
          <button
            onClick={() => setActiveTab('dubbing')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === 'dubbing'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
            }`}
          >
            Paso 2: Doblaje (TTS)
          </button>
          <button
            onClick={() => setActiveTab('studio')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === 'studio'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/20'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/60'
            }`}
          >
            Paso 3: Estudio de Mezcla
          </button>
        </nav>

        {/* Right: Language & Pinokio Status */}
        <div className="flex items-center gap-3">
          {currentProject ? (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-neutral-800/80 border border-neutral-700/60 text-neutral-300">
              <span>{language === 'pt' ? '🇧🇷 Portugués' : '🇺🇸 Inglés'}</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-neutral-800/40 border border-neutral-700/40 text-neutral-500">
              <span>Sin proyecto</span>
            </div>
          )}

          <button
            onClick={toggleTTSModel}
            disabled={isTTSToggling}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition shadow-sm ${
              isTTSToggling
                ? 'bg-amber-500/15 border-amber-500/50 text-amber-300 animate-pulse cursor-wait'
                : isTTSLoaded
                ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300 hover:bg-emerald-500/30 shadow-emerald-950/40'
                : 'bg-neutral-800/90 border-neutral-700 text-neutral-300 hover:bg-neutral-700 hover:text-white'
            }`}
            title={
              isTTSToggling
                ? 'Procesando en GPU...'
                : isTTSLoaded
                ? 'Modelo Qwen3-TTS montado en GPU (VRAM activa). Haz clic para desmontarlo y liberar memoria.'
                : 'Modelo Qwen3-TTS no montado. Haz clic para montarlo en VRAM y dejarlo listo para doblar instantáneamente.'
            }
          >
            <Radio className={`w-3.5 h-3.5 ${isTTSToggling ? 'animate-spin' : isTTSLoaded ? 'text-emerald-400' : 'text-neutral-400'}`} />
            <span>
              {isTTSToggling
                ? (isTTSLoaded ? 'Desmontando...' : 'Montando en VRAM...')
                : isTTSLoaded
                ? '🟢 Qwen TTS Listo'
                : '⚡ Montar Qwen TTS'}
            </span>
          </button>
        </div>
      </div>

      {/* New Project Modal (Portaled to document.body to avoid header backdrop-blur positioning traps) */}
      {isNewProjectModalOpen &&
        createPortal(
          <div className="fixed inset-0 z-[9999] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
            <div className="bg-neutral-900 border border-neutral-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 my-auto relative animate-in fade-in zoom-in-95 duration-150">
              <h3 className="text-base font-bold text-white">Crear Nuevo Proyecto</h3>
              
              <div className="space-y-3 text-sm">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">Nombre del Proyecto</label>
                  <input
                    type="text"
                    placeholder="ej. tutorial_instalacion_plantillas"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-white outline-none focus:border-sky-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">Ruta del Audio o Video Original (.wav / .mp4)</label>
                  <input
                    type="text"
                    placeholder="F:\Desarrollo\video.mp4"
                    value={newMediaPath}
                    onChange={(e) => setNewMediaPath(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-white outline-none focus:border-sky-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">Idioma de Doblaje</label>
                  <select
                    value={newLang}
                    onChange={(e) => setNewLang(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-white outline-none focus:border-sky-500"
                  >
                    <option value="en">Inglés (English)</option>
                    <option value="pt">Portugués (Brasil)</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  onClick={() => setIsNewProjectModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-xs font-semibold text-neutral-400 hover:text-white transition"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleCreate}
                  disabled={isCreating}
                  className="px-4 py-2 rounded-lg text-xs font-semibold bg-sky-500 hover:bg-sky-400 text-white transition disabled:opacity-50"
                >
                  {isCreating ? 'Creando...' : 'Crear Proyecto'}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </header>
  );
};

