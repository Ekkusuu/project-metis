import { useState } from 'react';
import RagPanel from './RagPanel';
import ChatsPanel from './ChatsPanel';
import SettingsPanel from './SettingsPanel';
import { BookIcon, ChatBubbleIcon, SlidersIcon } from './Icons';
import './Sidebar.css';

type Tab = 'rag' | 'chats';

function Sidebar() {
  const [activeTab, setActiveTab] = useState<Tab>('rag');
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-topbar">
          <div className="sidebar-tabs">
            <button
              className={`tab-button ${activeTab === 'rag' ? 'active' : ''}`}
              onClick={() => setActiveTab('rag')}
            >
              <BookIcon className="tab-icon" />
              <span>RAG</span>
            </button>
            <button
              className={`tab-button ${activeTab === 'chats' ? 'active' : ''}`}
              onClick={() => setActiveTab('chats')}
            >
              <ChatBubbleIcon className="tab-icon" />
              <span>Chats</span>
            </button>
          </div>

          <button
            className="sidebar-settings-button"
            onClick={() => setSettingsOpen(true)}
            title="Open settings"
          >
            <SlidersIcon className="tab-icon" />
          </button>
        </div>

        <div className="sidebar-content">
          {activeTab === 'rag' ? <RagPanel /> : <ChatsPanel />}
        </div>
      </div>

      {settingsOpen && (
        <div className="settings-modal-overlay" onClick={() => setSettingsOpen(false)}>
          <div className="settings-modal-shell" onClick={(e) => e.stopPropagation()}>
            <SettingsPanel onClose={() => setSettingsOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}

export default Sidebar;
