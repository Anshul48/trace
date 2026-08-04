import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
  const [isPreview, setIsPreview] = useState(true);
  
  // Throttle timer for autosave
  const [saveTimer, setSaveTimer] = useState<any>(null);

  useEffect(() => {
    // Fetch initial TOC
    fetch(`${API_BASE}/api/projects/${id}/toc`)
      .then(res => res.json())
      .then(data => setToc(data.toc || '# Table of Contents\n\nNo content generated yet.'))
      .catch(err => console.error(err));

    // Connect WebSocket
    const wsBase = API_BASE.replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsBase}/api/ws/logs/${id}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'TocGenerated') {
          setToc(data.payload.global_toc);
          setIsSynthesizing(false);
          setChat(prev => [...prev, { role: 'bot', content: 'TOC generation complete.' }]);
        }
      } catch (e) {
        console.error('Failed to parse WS message', e);
      }
    };

    return () => {
      ws.close();
    };
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
  
  const handleRegenerate = async () => {
    setIsSynthesizing(true);
    setChat(prev => [...prev, { role: 'bot', content: 'Planner is analyzing the knowledge graph and drafting a new TOC... this may take a moment.' }]);
    try {
      await fetch(`${API_BASE}/api/projects/${id}/synthesize`, { method: 'POST' });
    } catch (e) {
      console.error(e);
      setIsSynthesizing(false);
      setChat(prev => [...prev, { role: 'bot', content: 'Error generating TOC.' }]);
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
    <div className="animate-fade-in flex gap-6" style={{ height: '100%', minHeight: '600px' }}>
      {/* Left Panel: Markdown Editor */}
      <div className="glass-panel flex-1 flex flex-col" style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="flex items-center gap-4" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ color: 'var(--text-primary)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              ~/TOC.md
            </span>
            {isSaving && <span style={{ color: 'var(--accent-secondary)', fontSize: '0.8rem', fontWeight: '500' }} className="animate-pulse">saving...</span>}
            <div style={{ display: 'flex', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '4px' }}>
              <button 
                style={{
                  padding: '4px 12px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '0.85rem',
                  fontWeight: '500',
                  background: isPreview ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: isPreview ? 'white' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onClick={() => setIsPreview(true)}
              >
                Preview
              </button>
              <button 
                style={{
                  padding: '4px 12px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '0.85rem',
                  fontWeight: '500',
                  background: !isPreview ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: !isPreview ? 'white' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onClick={() => setIsPreview(false)}
              >
                Edit Raw
              </button>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={handleRegenerate} disabled={isWriting || isSynthesizing}>
              Regenerate TOC
            </button>
            <button className="btn btn-primary" onClick={handleFinalize} disabled={isWriting || isSynthesizing}>
              {isWriting ? 'Writing Repository...' : 'Finalize & Write'}
            </button>
          </div>
        </div>
        
        {isPreview ? (
          <div style={{ flex: 1, padding: '2rem', overflowY: 'auto', background: 'rgba(0,0,0,0.2)' }}>
            <div className="markdown-preview" style={{ maxWidth: '800px', margin: '0 auto', color: 'var(--text-primary)', lineHeight: '1.7' }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {toc}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          <textarea 
            style={{ 
              flex: 1,
              padding: '1.5rem',
              background: 'rgba(0,0,0,0.2)', 
              border: 'none', 
              color: 'var(--text-primary)', 
              fontFamily: 'monospace',
              resize: 'none',
              outline: 'none',
              fontSize: '14px',
              lineHeight: '1.6'
            }}
            value={toc}
            onChange={(e) => handleTocChange(e.target.value)}
          />
        )}
      </div>

      {/* Right Panel: Chat with Planner */}
      <div className="glass-panel w-96 flex flex-col" style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
          <span style={{ color: 'var(--text-primary)', fontWeight: '600' }}>Planner Agent</span>
        </div>
        
        <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', background: 'rgba(139, 92, 246, 0.05)', padding: '1rem', borderRadius: '8px', border: '1px solid rgba(139, 92, 246, 0.1)' }}>
            <strong style={{ color: 'var(--accent-primary)' }}>Planner:</strong> I have synthesized the initial Table of Contents. Edit it directly on the left, or chat with me to restructure it.
          </div>

          {chat.map((msg, i) => (
            <div key={i} style={{ 
              background: msg.role === 'user' ? 'rgba(255,255,255,0.05)' : 'rgba(139, 92, 246, 0.05)',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              fontSize: '0.9rem',
              marginLeft: msg.role === 'user' ? '2rem' : '0',
              marginRight: msg.role === 'user' ? '0' : '2rem',
              border: msg.role === 'bot' ? '1px solid rgba(139, 92, 246, 0.1)' : '1px solid transparent',
              color: 'var(--text-primary)',
              lineHeight: '1.5'
            }}>
              <div style={{ color: msg.role === 'user' ? 'var(--text-secondary)' : 'var(--accent-primary)', fontSize: '0.75rem', marginBottom: '0.25rem', fontWeight: '600', textTransform: 'uppercase' }}>
                {msg.role}
              </div>
              {msg.content}
            </div>
          ))}

          {isSynthesizing && (
            <div style={{ color: 'var(--accent-secondary)', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }} className="animate-pulse">
              <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              Planner is revising TOC...
            </div>
          )}
        </div>

        <form onSubmit={handleSend} style={{ padding: '1rem', borderTop: '1px solid var(--border-color)', display: 'flex', gap: '0.5rem' }}>
          <input 
            className="input-field"
            placeholder="Tell planner how to restructure..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isSynthesizing || isWriting}
            style={{ flex: 1 }}
          />
          <button type="submit" className="btn btn-primary" disabled={isSynthesizing || isWriting || !input.trim()} style={{ padding: '0 1rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </form>
      </div>
    </div>
  );
}
