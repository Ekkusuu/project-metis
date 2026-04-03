import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import './ChatInterface.css';
import 'highlight.js/styles/github-dark.css';
import { API_URL } from '../lib/api';
import PlanPanel, { type PlanTask } from './PlanPanel';
import { EditIcon, PlusIcon } from './Icons';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'ai';
  timestamp: Date;
  tokensPerSecond?: number;
  planningNotes?: Array<{
    taskId?: string;
    taskContent?: string;
    note: string;
  }>;
}

interface ChatSummary {
  id: string;
  title: string;
  lastUpdated: string;
  messageCount: number;
  preview: string;
}

interface ChatLoadResponse {
  activeChatId: string | null;
  chats: ChatSummary[];
  chat: {
    chatId: string | null;
    title: string;
    messages: Array<Omit<Message, 'timestamp'> & { timestamp: string }>;
    lastUpdated: string;
  };
}

function PlanningTrace({ notes, messageId, isActive }: { notes: NonNullable<Message['planningNotes']>; messageId: string; isActive: boolean }) {
  const [open, setOpen] = useState(isActive);

  useEffect(() => {
    if (isActive) {
      setOpen(true);
    } else {
      setOpen(false);
    }
  }, [isActive]);

  if (!notes.length) return null;

  return (
    <div className="planning-trace">
      <button
        className="planning-trace-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={`${messageId}-planning-trace`}
      >
        <span>{open ? 'Hide planning trace' : 'Show planning trace'}</span>
        <span className="planning-trace-count">{notes.length}</span>
      </button>
      {open && (
        <div id={`${messageId}-planning-trace`} className="planning-trace-content">
          {notes.map((entry, index) => (
            <div key={`${messageId}-note-${index}`} className="planning-trace-item">
              {entry.taskContent && <div className="planning-trace-task">{entry.taskContent}</div>}
              <div className="planning-trace-note">{entry.note}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Component: render message text and split out any <think> sections.
function MessageText({ rawText, messageId }: { rawText: string; messageId: string }) {
  const normalize = (t: string) =>
    t
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/(\d+\.)[ \t]*\n+/g, '$1 ')
      .replace(/\n+(\d+\.)/g, '\n$1')
      .replace(/\n+[ \t]*([-*])\s/g, '\n$1 ')
      .replace(/([^\n])\n(?!\n)/g, '$1  \n');

  // Parse think blocks. Support three cases:
  // - <think>...</think>
  // - stray </think> (treat preceding text as thinking)
  // - stray <think> without close (treat rest as thinking)
  const parseParts = (text: string) => {
    const parts: Array<{ type: 'text' | 'think'; content: string }> = [];

    // If there's an opening tag without a closing tag, treat remainder as think
    if (/\<think\>/i.test(text) && !/\<\/think\>/i.test(text)) {
      const openIdx = text.search(/\<think\>/i);
      if (openIdx > -1) {
        const before = text.slice(0, openIdx);
        const thinkContent = text.slice(openIdx + 7);
        if (before) parts.push({ type: 'text', content: before });
        parts.push({ type: 'think', content: thinkContent });
        return parts;
      }
    }

    // Find normal <think>...</think> blocks
    const re = /<think>([\s\S]*?)<\/think>/i;
    let remaining = text;
    let m: RegExpExecArray | null;
    while ((m = re.exec(remaining)) !== null) {
      const idx = m.index;
      const before = remaining.slice(0, idx);
      if (before) parts.push({ type: 'text', content: before });
      parts.push({ type: 'think', content: m[1] });
      remaining = remaining.slice(idx + m[0].length);
    }

    // If there were no normal blocks but there's a stray closing tag, treat up-to-close as think
    if (parts.length === 0 && /<\/think>/i.test(remaining) && !/\<think\>/i.test(text)) {
      const closeIdx = remaining.search(/<\/think>/i);
      if (closeIdx > -1) {
        const thinkContent = remaining.slice(0, closeIdx);
        const after = remaining.slice(closeIdx + 8);
        parts.push({ type: 'think', content: thinkContent });
        if (after) parts.push({ type: 'text', content: after });
        return parts;
      }
    }

    if (remaining) parts.push({ type: 'text', content: remaining });
    return parts;
  };

  const parts = parseParts(rawText);

  return (
    <>
      {parts.map((p, i) =>
        p.type === 'text' ? (
          <ReactMarkdown key={`${messageId}-txt-${i}`} rehypePlugins={[rehypeHighlight]}>
            {normalize(p.content)}
          </ReactMarkdown>
        ) : (
          <div key={`${messageId}-think-${i}`} className="think-block">
            <div className="think-label">Thinking:</div>
            <div className="think-content">
              <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{normalize(p.content)}</ReactMarkdown>
            </div>
          </div>
        )
      )}
    </>
  );
}
function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [activeChatTitle, setActiveChatTitle] = useState('New chat');
  const [tasks, setTasks] = useState<PlanTask[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showTypingIndicator, setShowTypingIndicator] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const applyChatResponse = (data: ChatLoadResponse) => {
    setActiveChatId(data.activeChatId);
    setActiveChatTitle(data.chat.title);
    setMessages(data.chat.messages.map((msg) => ({ ...msg, timestamp: new Date(msg.timestamp) })));
    window.dispatchEvent(new CustomEvent('chatStateUpdated', { detail: { activeChatId: data.activeChatId, chats: data.chats } }));
  };

  const resetToFreshChat = () => {
    setActiveChatId(null);
    setActiveChatTitle('New chat');
    setMessages([]);
    setTasks([]);
    window.dispatchEvent(new CustomEvent('chatStateUpdated', { detail: { activeChatId: null, chats: [] } }));
  };

  // Load chat history on mount
  useEffect(() => {
    loadChatHistory();
  }, []);

  // Save chat history whenever messages change (but not on initial load)
  useEffect(() => {
    // Avoid saving while the AI is actively streaming tokens (isTyping)
    // Streaming updates mutate `messages` many times per response which causes
    // repeated POSTs to `/history/save`. Only save when not typing.
    if (!isLoading && !isTyping && activeChatId && messages.length > 0) {
      scheduleSave();
    }
  }, [messages, isTyping, isLoading, activeChatId]);

  // Also save once when a message has finished streaming. The streaming
  // handler dispatches a `messageComplete` CustomEvent when finished.
  useEffect(() => {
    const handleMessageComplete = () => {
      // Save safely (fire-and-forget)
      saveChatHistory();
    };

    window.addEventListener('messageComplete', handleMessageComplete);
    return () => window.removeEventListener('messageComplete', handleMessageComplete);
  }, []);

  useEffect(() => {
    const handleCreateRequested = () => {
      if (!isTyping && !isLoading) void handleCreateChat();
    };

    const handleSelectRequested = (event: Event) => {
      const chatId = (event as CustomEvent<{ chatId: string }>).detail?.chatId;
      if (!chatId || isTyping || isLoading) return;
      void selectChat(chatId);
    };

    window.addEventListener('requestNewChat', handleCreateRequested);
    window.addEventListener('requestSelectChat', handleSelectRequested);
    const handleChatResponseLoaded = (event: Event) => {
      const detail = (event as CustomEvent<ChatLoadResponse>).detail;
      if (!detail) return;
      applyChatResponse(detail);
    };
    const handleFreshChatReset = () => {
      resetToFreshChat();
    };

    window.addEventListener('chatResponseLoaded', handleChatResponseLoaded);
    window.addEventListener('chatResetToFresh', handleFreshChatReset);
    return () => {
      window.removeEventListener('requestNewChat', handleCreateRequested);
      window.removeEventListener('requestSelectChat', handleSelectRequested);
      window.removeEventListener('chatResponseLoaded', handleChatResponseLoaded);
      window.removeEventListener('chatResetToFresh', handleFreshChatReset);
    };
  }, [isTyping, isLoading, activeChatId, messages, activeChatTitle]);

  // Debounced save helper: prevents rapid consecutive POSTs if state updates
  // happen in bursts. `scheduleSave` will call `saveChatHistory` after a short
  // delay unless another save is scheduled.
  const saveTimeoutRef = useRef<number | null>(null);
  const scheduleSave = () => {
    if (saveTimeoutRef.current) {
      window.clearTimeout(saveTimeoutRef.current);
    }
    // Delay slightly to coalesce rapid updates
    saveTimeoutRef.current = window.setTimeout(() => {
      saveChatHistory();
      saveTimeoutRef.current = null;
    }, 800);
  };

  // Clear pending timeouts on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) window.clearTimeout(saveTimeoutRef.current);
    };
  }, []);

  const loadChatHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/history/load`);
      if (response.ok) {
        const data: ChatLoadResponse = await response.json();
        applyChatResponse(data);
      } else {
        resetToFreshChat();
      }
    } catch (error) {
      console.error('Failed to load chat history:', error);
      resetToFreshChat();
    } finally {
      setIsLoading(false);
    }
  };

  const selectChat = async (chatId: string) => {
    if (chatId === activeChatId) return;

    if (saveTimeoutRef.current) {
      window.clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
      await saveChatHistory();
    }

    setTasks([]);
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/history/load?chat_id=${encodeURIComponent(chatId)}`);
      if (!response.ok) throw new Error((await response.text()) || 'Failed to load selected chat');
      const data: ChatLoadResponse = await response.json();
      applyChatResponse(data);
    } catch (error) {
      console.error('Failed to switch chats:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateChat = async () => {
    if (saveTimeoutRef.current) {
      window.clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
      await saveChatHistory();
    }

    setTasks([]);
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/history/chats`, { method: 'POST' });
      if (!response.ok) throw new Error((await response.text()) || 'Failed to create chat');
      const data: ChatLoadResponse = await response.json();
      applyChatResponse(data);
      setInput('');
    } catch (error) {
      console.error('Failed to create chat:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const streamChatResponse = async (history: Array<{ role: string; content: string }>) => {
    setTasks([]);

    const resp = await fetch(`${API_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: history }),
    });

    if (!resp.ok) {
      const detail = await resp.text();
      throw new Error(`Backend error ${resp.status}: ${detail}`);
    }

    window.dispatchEvent(new CustomEvent('ragRetrievalComplete'));

    const reader = resp.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let firstTokenReceived = false;
    const aiMessageId = (Date.now() + 1).toString();
    let messageCreated = false;

    const ensureAiMessage = () => {
      if (messageCreated) return;
      messageCreated = true;
      const aiMessage: Message = {
        id: aiMessageId,
        text: '',
        sender: 'ai',
        timestamp: new Date(),
        planningNotes: [],
      };
      setMessages((prev) => [...prev, aiMessage]);
    };

    if (!reader) throw new Error('No response body');

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const chunk = JSON.parse(line);
          if (chunk.type === 'task_snapshot' && Array.isArray(chunk.tasks)) {
            setTasks(chunk.tasks);
            continue;
          }

          if (chunk.type === 'task_note' && chunk.note) {
            ensureAiMessage();
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === aiMessageId
                  ? {
                      ...msg,
                      planningNotes: [
                        ...(msg.planningNotes || []),
                        {
                          taskId: chunk.task_id,
                          taskContent: chunk.task_content,
                          note: chunk.note,
                        },
                      ],
                    }
                  : msg
              )
            );
            continue;
          }

          if (chunk.delta !== undefined && chunk.delta !== '') {
            if (!firstTokenReceived) {
              firstTokenReceived = true;
              setShowTypingIndicator(false);
              ensureAiMessage();
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === aiMessageId
                    ? { ...msg, text: chunk.delta }
                    : msg
                )
              );
            } else {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === aiMessageId
                    ? { ...msg, text: msg.text + chunk.delta }
                    : msg
                )
              );
            }
          }

          if (chunk.done) {
            if (Array.isArray(chunk.tasks)) {
              setTasks(chunk.tasks);
            }
            if (chunk.tokens_per_second) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === aiMessageId
                    ? { ...msg, tokensPerSecond: chunk.tokens_per_second }
                    : msg
                )
              );
            }

            if (chunk.trimmed_messages && Array.isArray(chunk.trimmed_messages)) {
              const trimmedCount = history.length - chunk.trimmed_messages.length;
              if (trimmedCount > 0) {
                console.log(`Context limit reached: removed ${trimmedCount} oldest message(s)`);
                setMessages((prev) => {
                  const messagesToKeep = prev.length - trimmedCount;
                  return prev.slice(-messagesToKeep);
                });
              }
            }
          }
        } catch (parseErr) {
          console.warn('Failed to parse chunk:', line, parseErr);
        }
      }
    }

    setIsTyping(false);
    setShowTypingIndicator(false);
    window.dispatchEvent(new CustomEvent('messageComplete'));
  };

  const saveChatHistory = async () => {
    if (!activeChatId) return;

    try {
      const response = await fetch(`${API_URL}/history/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chatId: activeChatId,
          title: activeChatTitle,
          messages: messages.map((msg) => ({
            ...msg,
            timestamp: msg.timestamp.toISOString(),
          })),
          lastUpdated: new Date().toISOString(),
        }),
      });
      if (response.ok) {
        const data: ChatLoadResponse = await response.json();
        setActiveChatTitle(data.chat.title);
        window.dispatchEvent(new CustomEvent('chatStateUpdated', { detail: { activeChatId: data.activeChatId, chats: data.chats } }));
      }
    } catch (error) {
      console.error('Failed to save chat history:', error);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const autoResizeTextarea = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    autoResizeTextarea();
  }, [input]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: input,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);
    setShowTypingIndicator(true);
    
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    // Streaming API call
    try {
      let ensuredChatId = activeChatId;
      if (!ensuredChatId) {
        const createResponse = await fetch(`${API_URL}/history/chats`, { method: 'POST' });
        if (!createResponse.ok) throw new Error((await createResponse.text()) || 'Failed to create chat');
        const created: ChatLoadResponse = await createResponse.json();
        ensuredChatId = created.activeChatId;
        setActiveChatId(created.activeChatId);
        setActiveChatTitle(created.chat.title);
        window.dispatchEvent(new CustomEvent('chatStateUpdated', { detail: { activeChatId: created.activeChatId, chats: created.chats } }));
      }

      const history = [
        ...messages.map((m) => ({
          role: m.sender === 'user' ? 'user' : 'assistant',
          content: m.text,
        })),
        { role: 'user', content: userMessage.text },
      ];

      await streamChatResponse(history);
    } catch (err: any) {
      setIsTyping(false);
      setShowTypingIndicator(false);
      const errMsg: Message = {
        id: (Date.now() + 2).toString(),
        text: `Error contacting AI backend: ${err?.message || String(err)}`,
        sender: 'ai',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleEditMessage = (messageId: string, currentText: string) => {
    setEditingMessageId(messageId);
    setEditingText(currentText);
  };

  const handleCancelEdit = () => {
    setEditingMessageId(null);
    setEditingText('');
  };

  const handleSaveEdit = async (messageId: string) => {
    if (!editingText.trim()) return;

    // Find the index of the message being edited
    const messageIndex = messages.findIndex((m) => m.id === messageId);
    if (messageIndex === -1) return;

    // Delete all messages after this one
    const updatedMessages = messages.slice(0, messageIndex);
    
    // Update the edited message
    const editedMessage: Message = {
      ...messages[messageIndex],
      text: editingText,
      timestamp: new Date(),
    };

    setMessages([...updatedMessages, editedMessage]);
    setEditingMessageId(null);
    setEditingText('');
    setIsTyping(true);
    setShowTypingIndicator(true);

    // Send the edited message to get a new AI response
    try {
      const history = [
        ...updatedMessages.map((m) => ({
          role: m.sender === 'user' ? 'user' : 'assistant',
          content: m.text,
        })),
        { role: 'user', content: editingText },
      ];

      await streamChatResponse(history);
    } catch (err: any) {
      setIsTyping(false);
      setShowTypingIndicator(false);
      const errMsg: Message = {
        id: (Date.now() + 2).toString(),
        text: `Error contacting AI backend: ${err?.message || String(err)}`,
        sender: 'ai',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    }
  };

  return (
    <div className="chat-shell">
      <div className="chat-container">
      <div className="chat-header">
        <div className="header-content">
          <div className="header-text">
            <h1>{activeChatTitle}</h1>
            <p className="subtitle">Your AI Assistant</p>
          </div>
          <button onClick={handleCreateChat} className="reset-button" title="New chat" disabled={isTyping || isLoading}>
            <PlusIcon className="button-icon" />
            <span>New chat</span>
          </button>
        </div>
      </div>

      <div className="messages-container">
        {isLoading ? (
          <div className="loading-history">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <p>Loading chat history...</p>
          </div>
        ) : (
          <>
            {messages.map((message) => {
              const isLatestMessage = message.id === messages[messages.length - 1]?.id;
              const isStreamingMessage = message.sender === 'ai' && isTyping && isLatestMessage;
              const showPlanningTrace = isStreamingMessage && message.text.trim().length === 0;

              return (
          <div
            key={message.id}
            className={`message ${message.sender === 'user' ? 'user-message' : 'ai-message'}`}
          >
            <div className={`message-content ${isStreamingMessage ? 'streaming-message-content' : ''}`}>
              {editingMessageId === message.id ? (
                // Edit mode
                <div className="edit-mode">
                  <textarea
                    value={editingText}
                    onChange={(e) => setEditingText(e.target.value)}
                    className="edit-textarea"
                    autoFocus
                  />
                  <div className="edit-buttons">
                    <button onClick={() => handleSaveEdit(message.id)} className="save-edit-button">
                      Save
                    </button>
                    <button onClick={handleCancelEdit} className="cancel-edit-button">
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                // Normal display mode
                <>
                  <div className="message-text">
                    <MessageText rawText={message.text} messageId={message.id} />
                  </div>
                  {message.sender === 'user' && (
                    <button
                      onClick={() => handleEditMessage(message.id, message.text)}
                    className="edit-message-button"
                    title="Edit message"
                  >
                      <EditIcon className="button-icon" />
                    </button>
                  )}
                  {message.sender === 'ai' && message.planningNotes && message.planningNotes.length > 0 && (
                    <PlanningTrace
                      notes={message.planningNotes}
                      messageId={message.id}
                      isActive={showPlanningTrace}
                    />
                  )}
                  {message.tokensPerSecond && (
                    <div className="message-meta" style={{ fontSize: '0.75rem', opacity: 0.6, marginTop: '4px' }}>
                      {message.tokensPerSecond} tokens/sec
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
              );
            })}
        {showTypingIndicator && (
          <div className="message ai-message">
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div className="input-container">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type your message..."
          rows={1}
          className="message-input"
          disabled={isTyping}
        />
        <button onClick={handleSend} className="send-button" disabled={isTyping}>
          {isTyping ? 'Wait...' : 'Send'}
        </button>
      </div>
      </div>
      <PlanPanel tasks={tasks} isTyping={isTyping} />
    </div>
  );
}

export default ChatInterface;
