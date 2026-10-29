import React, { useEffect } from 'react';
import { useProjectStore } from './stores/useProjectStore';
import { useWebSocket } from './hooks/useWebSocket';
import { Navbar } from './components/Navbar';
import { ScriptTab } from './views/ScriptTab';
import { DubbingTab } from './views/DubbingTab';
import { StudioTab } from './views/StudioTab';
import { Folder, Plus, Sparkles, ArrowRight } from 'lucide-react';

export const App: React.FC = () => {
  const {
    currentProject,
    projectsList,
    activeTab,
    loadProjectsList,
    selectProject,
    setIsNewProjectModalOpen,
    checkTTS,
  } = useProjectStore();

  // Active WebSocket listener
  useWebSocket();

  // Initial load: solo carga la lista de proyectos, sin abrir ninguno automáticamente
  useEffect(() => {
    loadProjectsList();
    checkTTS();

    // Check TTS periodically every 15s
    const timer = setInterval(() => checkTTS(), 15000);
    return () => clearInterval(timer);
  }, [loadProjectsList, checkTTS]);

  return (
    <div className="h-screen bg-neutral-950 text-neutral-100 flex flex-col font-sans overflow-hidden">
      <Navbar />

      <main className="flex-1 min-h-0 flex flex-col overflow-y-auto">
        {!currentProject ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-2xl mx-auto animate-in fade-in duration-200">
            <div className="w-16 h-16 rounded-2xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 mb-5 shadow-xl shadow-sky-500/5">
              <Sparkles className="w-8 h-8" />
            </div>

            <h1 className="text-2xl font-bold text-white mb-2 tracking-tight">
              Audio Dubbing Studio
            </h1>
            <p className="text-sm text-neutral-400 max-w-md mb-8 leading-relaxed">
              La aplicación ha iniciado en modo ligero sin precargar ningún proyecto pesado.
              Selecciona un proyecto para abrirlo o crea uno nuevo para comenzar.
            </p>

            <div className="w-full bg-neutral-900 border border-neutral-800 rounded-2xl p-6 shadow-xl">
              <div className="flex items-center justify-between pb-3 border-b border-neutral-800 mb-4">
                <span className="text-xs font-semibold text-neutral-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Folder className="w-3.5 h-3.5 text-sky-400" />
                  <span>Proyectos Disponibles ({projectsList.length})</span>
                </span>
                <button
                  onClick={() => setIsNewProjectModalOpen(true)}
                  className="px-2.5 py-1 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold flex items-center gap-1 transition shadow-sm shadow-sky-500/20"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Nuevo Proyecto</span>
                </button>
              </div>

              {projectsList.length === 0 ? (
                <div className="py-8 text-center text-neutral-500 text-xs">
                  No hay proyectos existentes. Crea tu primer proyecto para comenzar.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-72 overflow-y-auto pr-1">
                  {projectsList.map((p) => (
                    <button
                      key={p}
                      onClick={() => selectProject(p)}
                      className="flex items-center justify-between p-3 rounded-xl bg-neutral-950 hover:bg-neutral-800/80 border border-neutral-800 hover:border-sky-500/40 text-left transition group"
                    >
                      <div className="flex items-center gap-2.5 min-w-0 pr-2">
                        <Folder className="w-4 h-4 text-neutral-500 group-hover:text-sky-400 shrink-0 transition" />
                        <span className="text-xs font-semibold text-neutral-200 group-hover:text-white truncate">
                          {p}
                        </span>
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-neutral-600 group-hover:text-sky-400 group-hover:translate-x-0.5 transition shrink-0" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className={activeTab === 'script' ? 'flex-1 min-h-0 flex flex-col' : 'hidden'}>
              <ScriptTab />
            </div>
            <div className={activeTab === 'dubbing' ? 'flex-1 min-h-0 flex flex-col' : 'hidden'}>
              <DubbingTab />
            </div>
            <div className={activeTab === 'studio' ? 'block' : 'hidden'}>
              <StudioTab />
            </div>
          </>
        )}
      </main>
    </div>
  );
};
export default App;
