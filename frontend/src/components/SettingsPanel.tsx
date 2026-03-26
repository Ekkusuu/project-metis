import { useEffect, useMemo, useState } from 'react';
import { API_URL } from '../lib/api';
import { CloseIcon } from './Icons';
import './SettingsPanel.css';

type SettingsState = {
  chat: {
    system_prompt: string;
    temperature: number;
    top_p: number;
    max_tokens: number;
  };
  rag: {
    enabled: boolean;
    folders_to_index: string[];
    top_k: number;
    max_distance: number;
    use_reranker: boolean;
    reranker_top_k: number;
    reranker_min_score: number;
    query_generation_count: number;
  };
  memory: {
    temp_memory_token_limit: number;
    long_term_memory_token_limit: number;
  };
};

const defaultSettings: SettingsState = {
  chat: {
    system_prompt: '',
    temperature: 0.7,
    top_p: 0.95,
    max_tokens: 1024,
  },
  rag: {
    enabled: true,
    folders_to_index: ['docs', 'memory/long_term'],
    top_k: 6,
    max_distance: 1.5,
    use_reranker: true,
    reranker_top_k: 2,
    reranker_min_score: 0.1,
    query_generation_count: 3,
  },
  memory: {
    temp_memory_token_limit: 500,
    long_term_memory_token_limit: 5000,
  },
};

function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  const folderText = useMemo(() => settings.rag.folders_to_index.join('\n'), [settings.rag.folders_to_index]);

  const fetchSettings = async () => {
    try {
      const resp = await fetch(`${API_URL}/settings`);
      const data = await resp.json();
      setSettings(data.settings || defaultSettings);
    } catch (error) {
      console.error('Failed to fetch settings:', error);
      setMessage({ type: 'error', text: 'Failed to load settings.' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const updateSection = <K extends keyof SettingsState>(section: K, patch: Partial<SettingsState[K]>) => {
    setSettings((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        ...patch,
      },
    }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    setMessage({ type: 'info', text: 'Applying settings...' });

    try {
      const payload: SettingsState = {
        ...settings,
        rag: {
          ...settings.rag,
          folders_to_index: folderText
            .split('\n')
            .map((line) => line.trim().replace(/\\/g, '/'))
            .filter(Boolean),
        },
      };

      const resp = await fetch(`${API_URL}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(detail || 'Failed to save settings');
      }

      const data = await resp.json();
      setSettings(data.settings || payload);
      setMessage({
        type: 'success',
        text: data.reindexed ? 'Settings saved and knowledge base refreshed.' : 'Settings saved and applied.',
      });
      window.dispatchEvent(new CustomEvent('settingsUpdated'));
      window.dispatchEvent(new CustomEvent('messageComplete'));
      window.dispatchEvent(new CustomEvent('ragRetrievalComplete'));
    } catch (error: any) {
      console.error('Failed to save settings:', error);
      setMessage({ type: 'error', text: `Failed to save settings: ${error.message || error}` });
    } finally {
      setIsSaving(false);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  if (isLoading) {
    return (
      <div className="settings-panel settings-loading">
        <p>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <div>
          <h2>Settings</h2>
          <p>Change behavior and apply it live.</p>
        </div>
        <button className="settings-close" onClick={onClose} title="Close settings">
          <CloseIcon />
        </button>
      </div>

      <div className="settings-section">
        <h3>Chat</h3>
        <label className="settings-field settings-field-full">
          <span>System prompt</span>
          <textarea
            value={settings.chat.system_prompt}
            onChange={(e) => updateSection('chat', { system_prompt: e.target.value })}
            rows={8}
          />
        </label>
        <div className="settings-grid">
          <label className="settings-field">
            <span>Temperature</span>
            <input type="number" min="0" max="2" step="0.05" value={settings.chat.temperature} onChange={(e) => updateSection('chat', { temperature: Number(e.target.value) })} />
          </label>
          <label className="settings-field">
            <span>Top p</span>
            <input type="number" min="0" max="1" step="0.01" value={settings.chat.top_p} onChange={(e) => updateSection('chat', { top_p: Number(e.target.value) })} />
          </label>
          <label className="settings-field">
            <span>Max tokens</span>
            <input type="number" min="64" max="8192" step="1" value={settings.chat.max_tokens} onChange={(e) => updateSection('chat', { max_tokens: Number(e.target.value) })} />
          </label>
        </div>
      </div>

      <div className="settings-section">
        <h3>RAG</h3>
        <label className="settings-toggle">
          <input type="checkbox" checked={settings.rag.enabled} onChange={(e) => updateSection('rag', { enabled: e.target.checked })} />
          <span>Enable retrieval</span>
        </label>
        <label className="settings-field settings-field-full">
          <span>Folders to index</span>
          <textarea
            value={folderText}
            onChange={(e) => updateSection('rag', { folders_to_index: e.target.value.split('\n') })}
            rows={4}
          />
          <small>One folder per line. Relative paths work best in the app and release bundle.</small>
        </label>
        <div className="settings-grid">
          <label className="settings-field">
            <span>Top k</span>
            <input type="number" min="1" max="24" value={settings.rag.top_k} onChange={(e) => updateSection('rag', { top_k: Number(e.target.value) })} />
          </label>
          <label className="settings-field">
            <span>Max distance</span>
            <input type="number" min="-1" max="10" step="0.05" value={settings.rag.max_distance} onChange={(e) => updateSection('rag', { max_distance: Number(e.target.value) })} />
          </label>
          <label className="settings-field">
            <span>Query count</span>
            <input type="number" min="1" max="8" value={settings.rag.query_generation_count} onChange={(e) => updateSection('rag', { query_generation_count: Number(e.target.value) })} />
          </label>
        </div>
        <label className="settings-toggle">
          <input type="checkbox" checked={settings.rag.use_reranker} onChange={(e) => updateSection('rag', { use_reranker: e.target.checked })} />
          <span>Use reranker</span>
        </label>
        <div className="settings-grid">
          <label className="settings-field">
            <span>Reranker top k</span>
            <input type="number" min="1" max="24" value={settings.rag.reranker_top_k} onChange={(e) => updateSection('rag', { reranker_top_k: Number(e.target.value) })} />
          </label>
          <label className="settings-field">
            <span>Min rerank score</span>
            <input type="number" min="-1" max="10" step="0.05" value={settings.rag.reranker_min_score} onChange={(e) => updateSection('rag', { reranker_min_score: Number(e.target.value) })} />
          </label>
        </div>
      </div>

      <div className="settings-section">
        <h3>Memory</h3>
        <div className="settings-grid">
          <label className="settings-field">
            <span>Temp memory limit</span>
            <input type="number" min="100" max="50000" value={settings.memory.temp_memory_token_limit} onChange={(e) => updateSection('memory', { temp_memory_token_limit: Number(e.target.value) })} />
          </label>
          <label className="settings-field">
            <span>Long-term limit</span>
            <input type="number" min="500" max="100000" value={settings.memory.long_term_memory_token_limit} onChange={(e) => updateSection('memory', { long_term_memory_token_limit: Number(e.target.value) })} />
          </label>
        </div>
      </div>

      {message && <div className={`settings-message ${message.type}`}>{message.text}</div>}

      <div className="settings-actions">
        <button className="settings-save" onClick={handleSave} disabled={isSaving}>
          {isSaving ? 'Applying...' : 'Apply settings'}
        </button>
      </div>
    </div>
  );
}

export default SettingsPanel;
