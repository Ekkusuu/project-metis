import { useEffect, useState, type KeyboardEvent } from 'react';
import { API_URL } from '../lib/api';
import { CheckIcon, CloseIcon, EditIcon, TrashIcon } from './Icons';
import './ChatsPanel.css';

type ChatSummary = {
  id: string;
  title: string;
  lastUpdated: string;
  messageCount: number;
  preview: string;
};

type ChatListResponse = {
  activeChatId: string;
  chats: ChatSummary[];
};

type ChatStateEventDetail = ChatListResponse;

const handleChatRowKeyDown = (event: KeyboardEvent<HTMLDivElement>, chatId: string, disabled: boolean) => {
  if (disabled) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    window.dispatchEvent(new CustomEvent('requestSelectChat', { detail: { chatId } }));
  }
};

function ChatsPanel() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');

  const applyState = (data: ChatListResponse) => {
    setChats(data.chats);
    setActiveChatId(data.activeChatId);
  };

  useEffect(() => {
    const loadChats = async () => {
      try {
        const response = await fetch(`${API_URL}/history/chats`);
        if (!response.ok) throw new Error((await response.text()) || 'Failed to load chats');
        const data: ChatListResponse = await response.json();
        applyState(data);
      } catch (error) {
        console.error('Failed to load chats:', error);
      } finally {
        setIsLoading(false);
      }
    };

    const handleStateUpdated = (event: Event) => {
      const detail = (event as CustomEvent<ChatStateEventDetail>).detail;
      if (!detail) return;
      applyState(detail);
    };

    loadChats();
    window.addEventListener('chatStateUpdated', handleStateUpdated);
    return () => window.removeEventListener('chatStateUpdated', handleStateUpdated);
  }, []);

  const formatLastActive = (lastUpdated: string) => {
    const updatedAt = new Date(lastUpdated).getTime();
    if (Number.isNaN(updatedAt)) return 'last active recently';
    const diffMs = Date.now() - updatedAt;
    const days = Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
    if (days === 0) return 'last active today';
    if (days === 1) return 'last active 1 day ago';
    return `last active ${days} days ago`;
  };

  const startRenameChat = (chat: ChatSummary) => {
    setEditingChatId(chat.id);
    setDraftTitle(chat.title);
  };

  const cancelRenameChat = () => {
    setEditingChatId(null);
    setDraftTitle('');
  };

  const handleRenameChat = async (chat: ChatSummary) => {
    const nextTitle = draftTitle.trim();
    if (!nextTitle) return;
    if (nextTitle === chat.title) {
      cancelRenameChat();
      return;
    }

    try {
      const response = await fetch(`${API_URL}/history/chats/${encodeURIComponent(chat.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: nextTitle }),
      });
      if (!response.ok) throw new Error((await response.text()) || 'Failed to rename chat');
      const data = await response.json();
      applyState(data);
      window.dispatchEvent(new CustomEvent('chatStateUpdated', { detail: { activeChatId: data.activeChatId, chats: data.chats } }));
    } catch (error) {
      console.error('Failed to rename chat:', error);
    } finally {
      cancelRenameChat();
    }
  };

  const handleDeleteChat = async (chat: ChatSummary) => {
    if (!window.confirm(`Delete chat "${chat.title}"?`)) return;

    try {
      const response = await fetch(`${API_URL}/history/chats/${encodeURIComponent(chat.id)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error((await response.text()) || 'Failed to delete chat');
      const data = await response.json();
      applyState(data);
      window.dispatchEvent(new CustomEvent('chatResponseLoaded', { detail: data }));
      window.dispatchEvent(new CustomEvent('chatStateUpdated', { detail: { activeChatId: data.activeChatId, chats: data.chats } }));
      if (!data.activeChatId) {
        window.dispatchEvent(new CustomEvent('chatResetToFresh'));
      }
      if (editingChatId === chat.id) cancelRenameChat();
    } catch (error) {
      console.error('Failed to delete chat:', error);
    }
  };

  return (
    <div className="chats-panel">
      <div className="chats-panel-header">
        <div>
          <h2>Chats</h2>
          <p>{chats.length > 0 ? 'Saved conversations for this workspace' : 'Waiting for the first conversation'}</p>
        </div>
        <span className="chats-panel-status">{activeChatId ? 'ACTIVE' : 'IDLE'}</span>
      </div>
      <div className="chats-panel-list">
        {isLoading ? (
          <div className="chats-panel-empty">Loading chats...</div>
        ) : chats.length === 0 ? (
          <div className="chats-panel-empty">No chats yet.</div>
        ) : (
          chats.map((chat) => (
            <div
              key={chat.id}
              className={`chats-panel-item ${chat.id === activeChatId ? 'active' : ''}`}
              onClick={() => {
                if (chat.id === activeChatId) return;
                window.dispatchEvent(new CustomEvent('requestSelectChat', { detail: { chatId: chat.id } }));
              }}
              onKeyDown={(event) => handleChatRowKeyDown(event, chat.id, chat.id === activeChatId)}
              role="button"
              tabIndex={chat.id === activeChatId ? -1 : 0}
              aria-disabled={chat.id === activeChatId}
              title={chat.title}
            >
              <div className="chats-panel-item-prefix">{String(chats.findIndex((item) => item.id === chat.id) + 1).padStart(2, '0')}</div>
              <div className="chats-panel-item-body">
                <div className="chats-panel-item-line">
                  <span className="chats-panel-item-marker">{chat.id === activeChatId ? '[>]' : '[ ]'}</span>
                  {editingChatId === chat.id ? (
                    <div
                      className="chats-panel-item-rename"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <input
                        value={draftTitle}
                        onChange={(event) => setDraftTitle(event.target.value)}
                        className="chats-panel-item-input"
                        placeholder="Chat name"
                        autoFocus
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            void handleRenameChat(chat);
                          }
                          if (event.key === 'Escape') {
                            event.preventDefault();
                            cancelRenameChat();
                          }
                        }}
                      />
                      <button className="chats-panel-item-action save" onClick={() => void handleRenameChat(chat)} title="Save name" aria-label={`Save ${chat.title}`}>
                        <CheckIcon />
                      </button>
                      <button className="chats-panel-item-action" onClick={cancelRenameChat} title="Cancel rename" aria-label={`Cancel renaming ${chat.title}`}>
                        <CloseIcon />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="chats-panel-item-title" title={chat.title}>{chat.title}</div>
                      <div className="chats-panel-item-actions" onClick={(event) => event.stopPropagation()}>
                        <button
                          className="chats-panel-item-edit"
                          onClick={() => startRenameChat(chat)}
                          title="Rename chat"
                          aria-label={`Rename ${chat.title}`}
                        >
                          <EditIcon />
                        </button>
                        <button
                          className="chats-panel-item-edit delete"
                          onClick={() => void handleDeleteChat(chat)}
                          title="Delete chat"
                          aria-label={`Delete ${chat.title}`}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    </>
                  )}
                </div>
                <div className="chats-panel-item-preview">{formatLastActive(chat.lastUpdated)}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ChatsPanel;
