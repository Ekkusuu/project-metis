import { useState } from 'react';
import RagPanel from './RagPanel';
import ChatContext from './ChatContext';
import { BookIcon, ChatBubbleIcon } from './Icons';
import './Sidebar.css';

type Tab = 'rag' | 'context';

function Sidebar() {
  const [activeTab, setActiveTab] = useState<Tab>('rag');

  return (
    <div className="sidebar">
      <div className="sidebar-tabs">
        <button
          className={`tab-button ${activeTab === 'rag' ? 'active' : ''}`}
          onClick={() => setActiveTab('rag')}
        >
          <BookIcon className="tab-icon" />
          <span>RAG</span>
        </button>
        <button
          className={`tab-button ${activeTab === 'context' ? 'active' : ''}`}
          onClick={() => setActiveTab('context')}
        >
          <ChatBubbleIcon className="tab-icon" />
          <span>Context</span>
        </button>
      </div>

      <div className="sidebar-content">
        {activeTab === 'rag' ? <RagPanel /> : <ChatContext />}
      </div>
    </div>
  );
}

export default Sidebar;
