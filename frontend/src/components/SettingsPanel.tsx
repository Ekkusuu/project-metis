import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { API_URL } from '../lib/api';
import { CloseIcon, TrashIcon } from './Icons';
import './SettingsPanel.css';

type SettingsState = {
  chat: { system_prompt: string; temperature: number; top_p: number; max_tokens: number };
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
  memory: { temp_memory_token_limit: number; long_term_memory_token_limit: number };
};

type SettingsPreset = {
  id: string;
  title: string;
  description: string;
  settings: SettingsState;
  readonly?: boolean;
};

const defaultSettings: SettingsState = {
  chat: { system_prompt: 'You are Metis, a helpful AI assistant.', temperature: 0.7, top_p: 0.95, max_tokens: 512 },
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
  memory: { temp_memory_token_limit: 500, long_term_memory_token_limit: 5000 },
};

function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [folderText, setFolderText] = useState(defaultSettings.rag.folders_to_index.join('\n'));
  const [presets, setPresets] = useState<SettingsPreset[]>([]);
  const [currentPreset, setCurrentPreset] = useState<SettingsPreset | null>(null);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  const [editingPresetId, setEditingPresetId] = useState<string | null>(null);
  const [presetEditorOpen, setPresetEditorOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftDescription, setDraftDescription] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const messageTimeoutRef = useRef<number | null>(null);

  const presetItems = currentPreset ? [currentPreset, ...presets] : presets;
  const isDefaultSelected = activePresetId === null;
  const isCreatingPreset = presetEditorOpen && editingPresetId === null;
  const isEditingPreset = editingPresetId !== null;
  const isPresetMetadataEditable = isCreatingPreset || isEditingPreset;
  const selectedPreset = activePresetId ? presets.find((item) => item.id === activePresetId) ?? null : currentPreset;

  const setDraftSettings = (nextSettings: SettingsState) => {
    setSettings(nextSettings);
    setFolderText(nextSettings.rag.folders_to_index.join('\n'));
  };

  const buildPayload = (): SettingsState => ({
    ...settings,
    rag: {
      ...settings.rag,
      folders_to_index: folderText.split('\n').map((line) => line.trim().replace(/\\/g, '/')).filter(Boolean),
    },
  });

  const builtSettings = buildPayload();
  const hasPresetSettingsChanges = isEditingPreset && !!selectedPreset && JSON.stringify(builtSettings) !== JSON.stringify(selectedPreset.settings);
  const hasPresetMetadataChanges = isEditingPreset && !!selectedPreset && (draftTitle !== selectedPreset.title || draftDescription !== selectedPreset.description);
  const canSavePresetChanges = !isDefaultSelected && (isCreatingPreset || hasPresetSettingsChanges || hasPresetMetadataChanges);

  const showTemporaryMessage = (type: 'success' | 'error' | 'info', text: string) => {
    if (messageTimeoutRef.current) {
      window.clearTimeout(messageTimeoutRef.current);
      messageTimeoutRef.current = null;
    }
    setMessage({ type, text });
    if (type !== 'info') {
      messageTimeoutRef.current = window.setTimeout(() => {
        setMessage(null);
        messageTimeoutRef.current = null;
      }, 5000);
    }
  };

  const syncFromResponse = (data: any, fallbackSettings?: SettingsState) => {
    if (data.settings) setDraftSettings(data.settings);
    else if (fallbackSettings) setDraftSettings(fallbackSettings);
    if (data.current_preset) setCurrentPreset(data.current_preset);
    if (Array.isArray(data.presets)) setPresets(data.presets);
    if (Object.prototype.hasOwnProperty.call(data, 'active_preset_id')) setActivePresetId(data.active_preset_id || null);
  };

  const fetchSettings = async () => {
    try {
      const resp = await fetch(`${API_URL}/settings`);
      if (!resp.ok) throw new Error((await resp.text()) || 'Failed to load settings');
      const data = await resp.json();
      syncFromResponse(data, defaultSettings);
    } catch (error) {
      console.error('Failed to fetch settings:', error);
      setMessage({ type: 'error', text: 'Failed to load settings.' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    return () => {
      if (messageTimeoutRef.current) window.clearTimeout(messageTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (isCreatingPreset) return;

    if (activePresetId) {
      const preset = presets.find((item) => item.id === activePresetId);
      if (!preset) return;
      setEditingPresetId(preset.id);
      setDraftTitle(preset.title);
      setDraftDescription(preset.description);
      setPresetEditorOpen(true);
      return;
    }

    setEditingPresetId(null);
    setDraftTitle(currentPreset?.title ?? '');
    setDraftDescription(currentPreset?.description ?? '');
    setPresetEditorOpen(false);
  }, [activePresetId, currentPreset, presets, isCreatingPreset]);

  const updateSection = <K extends keyof SettingsState>(section: K, patch: Partial<SettingsState[K]>) => {
    setSettings((prev) => ({ ...prev, [section]: { ...prev[section], ...patch } }));
  };

  const dispatchSettingsAppliedEvents = () => {
    window.dispatchEvent(new CustomEvent('settingsUpdated'));
    window.dispatchEvent(new CustomEvent('messageComplete'));
    window.dispatchEvent(new CustomEvent('ragRetrievalComplete'));
  };

  const handlePresetRowKeyDown = (event: KeyboardEvent<HTMLDivElement>, onActivate: () => void) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onActivate();
    }
  };

  const startNewPreset = () => {
    setEditingPresetId(null);
    setDraftTitle('');
    setDraftDescription('');
    setPresetEditorOpen(true);
  };

  const savePresetChanges = async () => {
    if (isDefaultSelected) return;
    if (!draftTitle.trim()) {
      showTemporaryMessage('error', 'Preset title is required.');
      return;
    }
    setIsSaving(true);
    setMessage({ type: 'info', text: isCreatingPreset ? 'Saving preset...' : 'Saving changes...' });
    try {
      const payload = { title: draftTitle, description: draftDescription, settings: builtSettings };
      const resp = await fetch(editingPresetId ? `${API_URL}/settings/presets/${editingPresetId}` : `${API_URL}/settings/presets`, {
        method: editingPresetId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error((await resp.text()) || 'Failed to save preset');
      const data = await resp.json();
      const savedPresetId = editingPresetId ?? data.preset?.id;
      if (!savedPresetId) throw new Error('Saved preset id missing');

      setPresetEditorOpen(false);

      const applyResp = await fetch(`${API_URL}/settings/presets/${savedPresetId}/apply`, { method: 'PUT' });
      if (!applyResp.ok) throw new Error((await applyResp.text()) || 'Failed to apply preset');
      const applyData = await applyResp.json();
      syncFromResponse(applyData, builtSettings);
      showTemporaryMessage('success', applyData.reindexed ? 'Changes saved and knowledge base refreshed.' : 'Changes saved and applied.');
      dispatchSettingsAppliedEvents();
    } catch (error: any) {
      showTemporaryMessage('error', `Failed to save changes: ${error.message || error}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleApplyPreset = async (presetId: string) => {
    if (presetId === 'current-settings') return;
    setPresetEditorOpen(false);
    setIsSaving(true);
    setMessage({ type: 'info', text: 'Applying preset...' });
    try {
      const resp = await fetch(`${API_URL}/settings/presets/${presetId}/apply`, { method: 'PUT' });
      if (!resp.ok) throw new Error((await resp.text()) || 'Failed to apply preset');
      const data = await resp.json();
      syncFromResponse(data);
      showTemporaryMessage('success', data.reindexed ? 'Preset applied and knowledge base refreshed.' : 'Preset applied.');
      dispatchSettingsAppliedEvents();
    } catch (error: any) {
      showTemporaryMessage('error', `Failed to apply preset: ${error.message || error}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSelectCurrentPreset = async () => {
    if (!currentPreset) return;
    setPresetEditorOpen(false);
    setIsSaving(true);
    setMessage({ type: 'info', text: 'Selecting default settings...' });
    try {
      const resp = await fetch(`${API_URL}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentPreset.settings),
      });
      if (!resp.ok) throw new Error((await resp.text()) || 'Failed to select default settings');
      const data = await resp.json();
      syncFromResponse(data, currentPreset.settings);
      showTemporaryMessage('success', data.reindexed ? 'Default settings selected and knowledge base refreshed.' : 'Default settings selected.');
      dispatchSettingsAppliedEvents();
    } catch (error: any) {
      showTemporaryMessage('error', `Failed to select default settings: ${error.message || error}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeletePreset = async (presetId: string) => {
    setIsSaving(true);
    setMessage({ type: 'info', text: 'Deleting preset...' });
    try {
      const resp = await fetch(`${API_URL}/settings/presets/${presetId}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error((await resp.text()) || 'Failed to delete preset');
      const data = await resp.json();
      syncFromResponse(data);
      showTemporaryMessage('success', 'Preset deleted.');
    } catch (error: any) {
      showTemporaryMessage('error', `Failed to delete preset: ${error.message || error}`);
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) return <div className="settings-panel settings-loading"><p>Loading settings...</p></div>;

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <div>
          <h2>Settings</h2>
          <p>Change behavior, apply it live, and manage reusable presets.</p>
        </div>
        <button className="settings-close" onClick={onClose} title="Close settings"><CloseIcon /></button>
      </div>

      <div className="settings-layout">
        <div className="settings-sidebar-column">
          <div className="settings-section settings-presets-section">
            <div className="settings-section-topline">
              <div className="settings-section-heading">
                <h3>Presets</h3>
                <p className="settings-section-copy">Apply a saved setup instantly, or save whatever is currently configured on the right.</p>
              </div>
              <button className="settings-secondary settings-add-preset" onClick={startNewPreset} disabled={isSaving}>Add preset</button>
            </div>

            <div className="settings-presets-list">
              {presetItems.length === 0 && <div className="settings-presets-empty">No presets yet. Save the current configuration to create one.</div>}
              {presetItems.map((preset) => {
                const isActive = preset.readonly ? activePresetId === null : activePresetId === preset.id;
                if (preset.readonly) {
                  return (
                    <div
                      key={preset.id}
                      className={`settings-preset-row settings-preset-card ${isActive ? 'active' : ''} readonly`}
                      onClick={() => {
                        if (!isSaving) handleSelectCurrentPreset();
                      }}
                      onKeyDown={(event) => handlePresetRowKeyDown(event, handleSelectCurrentPreset)}
                      role="button"
                      tabIndex={isSaving ? -1 : 0}
                      aria-disabled={isSaving}
                    >
                      <span className="settings-preset-title-row">
                        <span className="settings-preset-title">{preset.title}</span>
                        <span className="settings-preset-badge">Default</span>
                      </span>
                      <span className="settings-preset-description">{preset.description || 'No description'}</span>
                    </div>
                  );
                }

                return (
                  <div
                    key={preset.id}
                    className={`settings-preset-row ${isActive ? 'active' : ''} ${preset.readonly ? 'readonly' : ''}`}
                    onClick={() => {
                      if (!isSaving) handleApplyPreset(preset.id);
                    }}
                    onKeyDown={(event) => handlePresetRowKeyDown(event, () => handleApplyPreset(preset.id))}
                    role="button"
                    tabIndex={isSaving ? -1 : 0}
                    aria-disabled={isSaving}
                  >
                    <div className="settings-preset-row-inner">
                      <div className="settings-preset-copy">
                        <div className="settings-preset-title-row">
                          <span className="settings-preset-title">{preset.title}</span>
                        </div>
                        <div className="settings-preset-description">{preset.description || 'No description'}</div>
                      </div>

                      {!preset.readonly && (
                        <div className="settings-preset-toolbar">
                          <button className="settings-icon-button" onClick={(e) => { e.stopPropagation(); handleDeletePreset(preset.id); }} title="Delete preset" disabled={isSaving}><TrashIcon /></button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="settings-content-column">
            <div className={`settings-section settings-preset-editor ${isPresetMetadataEditable ? 'visible' : ''}`}>
              <div className="settings-preset-editor-header">
                <div>
                  <div className="settings-preset-form-title">Preset details</div>
                  <div className="settings-preset-form-subtitle">
                  {isCreatingPreset
                    ? 'Name this preset, then save the settings configured below.'
                    : isEditingPreset
                      ? 'Update the selected preset metadata and save the current settings below.'
                      : 'Select a saved preset to edit its details, or click Add preset to create a new one.'}
                  </div>
                </div>
              </div>
              <div className="settings-preset-fields">
                <label className="settings-field"><span>Title</span><input value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} placeholder="Calm coach" disabled={!isPresetMetadataEditable} /></label>
                <label className="settings-field settings-field-full"><span>Description</span><input value={draftDescription} onChange={(e) => setDraftDescription(e.target.value)} placeholder="Warm tone, concise replies, retrieval on" disabled={!isPresetMetadataEditable} /></label>
              </div>
            </div>

          <div className={`settings-section ${isDefaultSelected ? 'settings-section-disabled' : ''}`}>
            <div className="settings-section-title-block">
              <h3>Chat</h3>
              <p className="settings-section-copy">Adjust how Metis responds before applying the changes live.</p>
            </div>
            <label className="settings-field settings-field-full"><span>System prompt</span><textarea value={settings.chat.system_prompt} onChange={(e) => updateSection('chat', { system_prompt: e.target.value })} rows={8} disabled={isDefaultSelected} /></label>
            <div className="settings-grid settings-grid-three">
              <label className="settings-field"><span>Temperature</span><input type="number" min="0" max="2" step="0.05" value={settings.chat.temperature} onChange={(e) => updateSection('chat', { temperature: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
              <label className="settings-field"><span>Top p</span><input type="number" min="0" max="1" step="0.01" value={settings.chat.top_p} onChange={(e) => updateSection('chat', { top_p: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
              <label className="settings-field"><span>Max tokens</span><input type="number" min="64" max="8192" step="1" value={settings.chat.max_tokens} onChange={(e) => updateSection('chat', { max_tokens: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
            </div>
          </div>

          <div className={`settings-section ${isDefaultSelected ? 'settings-section-disabled' : ''}`}>
            <div className="settings-section-title-block">
              <h3>RAG</h3>
              <p className="settings-section-copy">Control retrieval, indexing paths, and reranking behavior.</p>
            </div>
            <label className="settings-toggle"><input type="checkbox" checked={settings.rag.enabled} onChange={(e) => updateSection('rag', { enabled: e.target.checked })} disabled={isDefaultSelected} /><span>Enable retrieval</span></label>
            <label className="settings-field settings-field-full">
              <span>Folders to index</span>
              <textarea value={folderText} onChange={(e) => setFolderText(e.target.value)} rows={4} disabled={isDefaultSelected} />
              <small>One folder per line. Relative paths work best in the app and release bundle.</small>
            </label>
            <div className="settings-grid settings-grid-three">
              <label className="settings-field"><span>Top k</span><input type="number" min="1" max="24" value={settings.rag.top_k} onChange={(e) => updateSection('rag', { top_k: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
              <label className="settings-field"><span>Max distance</span><input type="number" min="-1" max="10" step="0.05" value={settings.rag.max_distance} onChange={(e) => updateSection('rag', { max_distance: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
              <label className="settings-field"><span>Query count</span><input type="number" min="1" max="8" value={settings.rag.query_generation_count} onChange={(e) => updateSection('rag', { query_generation_count: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
            </div>
            <label className="settings-toggle"><input type="checkbox" checked={settings.rag.use_reranker} onChange={(e) => updateSection('rag', { use_reranker: e.target.checked })} disabled={isDefaultSelected} /><span>Use reranker</span></label>
            <div className="settings-grid settings-grid-two">
              <label className="settings-field"><span>Reranker top k</span><input type="number" min="1" max="24" value={settings.rag.reranker_top_k} onChange={(e) => updateSection('rag', { reranker_top_k: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
              <label className="settings-field"><span>Min rerank score</span><input type="number" min="-1" max="10" step="0.05" value={settings.rag.reranker_min_score} onChange={(e) => updateSection('rag', { reranker_min_score: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
            </div>
          </div>

          <div className={`settings-section ${isDefaultSelected ? 'settings-section-disabled' : ''}`}>
            <div className="settings-section-title-block">
              <h3>Memory</h3>
              <p className="settings-section-copy">Tune temporary and long-term memory token budgets.</p>
            </div>
            <div className="settings-grid settings-grid-two">
              <label className="settings-field"><span>Temp memory limit</span><input type="number" min="100" max="50000" value={settings.memory.temp_memory_token_limit} onChange={(e) => updateSection('memory', { temp_memory_token_limit: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
              <label className="settings-field"><span>Long-term limit</span><input type="number" min="500" max="100000" value={settings.memory.long_term_memory_token_limit} onChange={(e) => updateSection('memory', { long_term_memory_token_limit: Number(e.target.value) })} disabled={isDefaultSelected} /></label>
            </div>
          </div>

          {message && <div className={`settings-message ${message.type}`}>{message.text}</div>}

        </div>
      </div>

      {canSavePresetChanges && (
        <div className="settings-actions">
          <button className="settings-save" onClick={savePresetChanges} disabled={isSaving || !draftTitle.trim()}>{isSaving ? 'Saving...' : 'Save changes'}</button>
        </div>
      )}
    </div>
  );
}

export default SettingsPanel;
