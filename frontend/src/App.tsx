import React, { useEffect } from 'react';
import { useProjectStore } from './stores/useProjectStore';
import { useWebSocket } from './hooks/useWebSocket';
import { Navbar } from './components/Navbar';
import { ScriptTab } from './views/ScriptTab';
import { DubbingTab } from './views/DubbingTab';
import { StudioTab } from './views/StudioTab';

export const App: React.FC = () => {
  const { activeTab, loadProjectsList, checkTTS } = useProjectStore();

  // Active WebSocket listener
  useWebSocket();

  // Initial load
  useEffect(() => {
    loadProjectsList();
    checkTTS();

    // Check TTS periodically every 15s
    const timer = setInterval(() => checkTTS(), 15000);
    return () => clearInterval(timer);
  }, [loadProjectsList, checkTTS]);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col font-sans">
      <Navbar />

      <main className="flex-1 pb-10">
        <div className={activeTab === 'script' ? 'block' : 'hidden'}>
          <ScriptTab />
        </div>
        <div className={activeTab === 'dubbing' ? 'block' : 'hidden'}>
          <DubbingTab />
        </div>
        <div className={activeTab === 'studio' ? 'block' : 'hidden'}>
          <StudioTab />
        </div>
      </main>
    </div>
  );
};
export default App;

