import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function TOCReviewer() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [toc, setToc] = useState('');
  const [chat, setChat] = useState<{role: 'user' | 'bot', content: string}[]>([]);
  const [input, setInput] = useState('');
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [isWriting, setIsWriting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  // Throttle timer for autosave
  const [saveTimer, setSaveTimer] = useState<any>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/projects/${id}/toc`)
      .then(res => res.json())
      .then(data => setToc(data.toc || '# Table of Contents\n\nNo content generated yet.'))
      .catch(err => console.error(err));
  }, [id]);

  const handleTocChange = (newVal: string) => {
    setToc(newVal);
    
    // Autosave functionality
    if (saveTimer) clearTimeout(saveTimer);
    setIsSaving(true);
    setSaveTimer(setTimeout(async () => {
      try {
        await fetch(`${API_BASE}/api/projects/${id}/toc`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ toc: newVal })
        });
      } catch (e) {
        console.error("Save failed", e);
      } finally {
        setIsSaving(false);
      }
    }, 1000));
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input;
    const newChatHistory = [...chat, { role: 'user' as const, content: userMsg }];
    setChat(newChatHistory);
    setInput('');
    setIsSynthesizing(true);

    try {
      const res = await fetch(`${API_BASE}/api/projects/${id}/toc/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_history: newChatHistory })
      });
      const data = await res.json();
      
      setChat([...newChatHistory, { role: 'bot', content: 'TOC updated.' }]);
      setToc(data.toc);
    } catch (e) {
      console.error(e);
      setChat([...newChatHistory, { role: 'bot', content: 'Error updating TOC.' }]);
    } finally {
      setIsSynthesizing(false);
    }
  };
  
  const handleFinalize = async () => {
    setIsWriting(true);
    try {
      await fetch(`${API_BASE}/api/projects/${id}/write`, { method: 'POST' });
      navigate(`/project/${id}/output`);
    } catch (e) {
      console.error(e);
      setIsWriting(false);
    }
  };

  return (
    <div className="animate-fade-in flex gap-6" style={{ height: 'calc(100vh - 120px)' }}>
      {/* Left Panel: Markdown Editor */}
      <div className="flex-1 flex flex-col" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
        <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <div className="flex items-center gap-2">
            <span style={{ color: 'var(--accent-primary)', fontWeight: 'bold' }}>~/pipeline/{id?.split('-')[0]}/TOC.md</span>
            {isSaving && <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>saving...</span>}
          </div>
          <button className="btn btn-primary" onClick={handleFinalize} disabled={isWriting || isSynthesizing}>
            {isWriting ? '[ WRITING... ]' : '[ FINALIZE & WRITE REPO ]'}
          </button>
        </div>
        
        <textarea 
          className="flex-1 p-4"
          style={{ 
            background: 'transparent', 
            border: 'none', 
            color: 'var(--text-primary)', 
            fontFamily: 'monospace',
            resize: 'none',
            outline: 'none',
            fontSize: '14px'
          }}
          value={toc}
          onChange={(e) => handleTocChange(e.target.value)}
        />
      </div>

      {/* Right Panel: Chat with Planner */}
      <div className="w-96 flex flex-col" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
        <div className="p-4" style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
          [ PLANNER AGENT ]
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
          <div style={{ color: 'var(--accent-primary)', fontSize: '0.875rem' }}>
            &gt; I have synthesized the initial Table of Contents. Edit it directly on the left, or chat with me to restructure it.
          </div>

          {chat.map((msg, i) => (
            <div key={i} style={{ 
              color: msg.role === 'user' ? 'var(--text-primary)' : 'var(--accent-primary)',
              fontSize: '0.875rem',
              marginLeft: msg.role === 'user' ? '1rem' : '0'
            }}>
              <span style={{ color: 'var(--text-muted)' }}>{msg.role === 'user' ? '$ user: ' : '> planner: '}</span>
              {msg.content}
            </div>
          ))}

          {isSynthesizing && (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }} className="animate-pulse">
              &gt; Planner is revising TOC...
            </div>
          )}
        </div>

        <form onSubmit={handleSend} className="p-4" style={{ borderTop: '1px solid var(--border-color)' }}>
          <div className="flex gap-2">
            <input 
              className="input-field"
              placeholder="$ prompt..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isSynthesizing || isWriting}
              style={{ background: 'var(--bg-primary)' }}
            />
            <button type="submit" className="btn btn-secondary" disabled={isSynthesizing || isWriting}>
              [SEND]
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
