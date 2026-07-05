import { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function PipelineLiveView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [logs, setLogs] = useState<{ id: number, type: 'info' | 'llm' | 'success', agent?: string, model?: string, prompt?: string, response?: string, msg?: string }[]>([]);
  const [isExtracting, setIsExtracting] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    if (!id) return;
    
    const wsBase = API_BASE.replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsBase}/api/ws/logs/${id}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "LLMCall") {
          setLogs(prev => [...prev, {
            id: Date.now(),
            type: 'llm',
            agent: data.payload.agent_name,
            model: data.payload.model_name,
            prompt: data.payload.prompt,
            response: data.payload.response
          }]);
        } else if (data.type === "TraceExtracted") {
          setLogs(prev => [...prev, {
            id: Date.now(),
            type: 'info',
            msg: `[EXTRACTED] trace: ${data.payload.trace.anchor_concept}`
          }]);
        } else if (data.type === "TocGenerated") {
          setLogs(prev => [...prev, {
            id: Date.now(),
            type: 'success',
            msg: `[COMPLETE] Pipeline paused. Awaiting user review of traces.`
          }]);
          setIsExtracting(false);
        } else {
          setLogs(prev => [...prev, {
            id: Date.now(),
            type: 'info',
            msg: `[SYS] ${data.type}`
          }]);
        }
      } catch (e) {
        console.error(e);
      }
    };
    
    ws.onclose = () => {
      setLogs(prev => [...prev, {
        id: Date.now(),
        type: 'info',
        msg: `[SYS] WebSocket connection closed.`
      }]);
      setIsExtracting(false);
    };

    return () => ws.close();
  }, [id]);

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 120px)' }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 style={{ fontSize: '1.25rem', color: 'var(--accent-primary)' }}>~/pipeline/{id?.split('-')[0]}</h1>
        </div>
        {!isExtracting && (
          <button className="btn btn-primary" onClick={() => navigate(`/project/${id}/traces`)}>
            [ REVIEW TRACES ]
          </button>
        )}
      </div>

      <div style={{ flex: 1, background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', padding: '1rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {logs.map(log => {
          const timeStr = new Date(log.id).toISOString().split('T')[1].slice(0, -1);
          
          if (log.type === 'info' || log.type === 'success') {
            const color = log.type === 'success' ? 'var(--success)' : 'var(--text-secondary)';
            return (
              <div key={log.id} style={{ display: 'flex', gap: '1rem', fontSize: '0.875rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>[{timeStr}]</span>
                <span style={{ color }}>{log.msg}</span>
              </div>
            );
          }
          
          if (log.type === 'llm') {
            return (
              <div key={log.id} style={{ borderLeft: '2px solid var(--accent-primary)', paddingLeft: '1rem', margin: '0.5rem 0', fontSize: '0.875rem' }}>
                <div style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                  [{timeStr}] <span style={{ color: 'var(--accent-secondary)' }}>{log.agent}</span> -&gt; {log.model}
                </div>
                <details style={{ cursor: 'pointer' }}>
                  <summary style={{ color: 'var(--text-primary)' }}>&gt; view payload</summary>
                  <div style={{ marginTop: '0.5rem', background: 'var(--bg-primary)', padding: '1rem', border: '1px solid var(--border-color)' }}>
                    <div style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }}>--- PROMPT ---</div>
                    <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: 'var(--text-secondary)' }}>{log.prompt}</pre>
                    <div style={{ color: 'var(--text-muted)', margin: '1rem 0 0.5rem 0' }}>--- RESPONSE ---</div>
                    <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: 'var(--accent-primary)' }}>{log.response}</pre>
                  </div>
                </details>
              </div>
            );
          }
          return null;
        })}
        {logs.length === 0 && <div style={{ color: 'var(--text-muted)' }}>&gt; waiting for stream...</div>}
        {isExtracting && <div style={{ color: 'var(--accent-primary)' }} className="animate-pulse">_</div>}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
