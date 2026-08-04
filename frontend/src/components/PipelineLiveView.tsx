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
    <div className="flex flex-col animate-fade-in" style={{ height: '100%', minHeight: '600px', gap: '2rem' }}>
      <div className="flex items-center justify-between">
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: '600', color: 'var(--text-primary)' }}>Ingestion Pipeline</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Live extraction stream for {id?.split('-')[0]}</p>
        </div>
        {!isExtracting && (
          <button className="btn btn-primary" onClick={() => navigate(`/project/${id}/traces`)}>
            Review Traces
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
          </button>
        )}
      </div>

      <div className="glass-panel" style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {logs.map(log => {
          const timeStr = new Date(log.id).toISOString().split('T')[1].slice(0, -1);
          
          if (log.type === 'info' || log.type === 'success') {
            const isSuccess = log.type === 'success';
            return (
              <div key={log.id} style={{ display: 'flex', gap: '1rem', fontSize: '0.9rem', alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>[{timeStr}]</span>
                <span style={{ color: isSuccess ? 'var(--success)' : 'var(--text-secondary)' }}>{log.msg}</span>
              </div>
            );
          }
          
          if (log.type === 'llm') {
            return (
              <div key={log.id} style={{ borderLeft: '2px solid var(--accent-primary)', paddingLeft: '1.5rem', margin: '0.5rem 0', fontSize: '0.9rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>[{timeStr}]</span>
                  <span style={{ color: 'var(--accent-secondary)', fontWeight: '500' }}>{log.agent}</span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{log.model}</span>
                </div>
                <details style={{ cursor: 'pointer' }}>
                  <summary style={{ color: 'var(--accent-primary)', outline: 'none', userSelect: 'none', fontWeight: '500' }}>View Payload</summary>
                  <div style={{ marginTop: '0.75rem', background: 'rgba(0,0,0,0.2)', padding: '1.5rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ color: 'var(--text-muted)', marginBottom: '0.5rem', fontSize: '0.8rem', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Prompt</div>
                    <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: 'var(--text-secondary)', fontFamily: 'monospace', fontSize: '0.85rem', lineHeight: '1.6' }}>{log.prompt}</pre>
                    <div style={{ color: 'var(--text-muted)', margin: '1.5rem 0 0.5rem 0', fontSize: '0.8rem', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Response</div>
                    <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: '0.85rem', lineHeight: '1.6' }}>{log.response}</pre>
                  </div>
                </details>
              </div>
            );
          }
          return null;
        })}
        {logs.length === 0 && (
          <div style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            Waiting for stream...
          </div>
        )}
        {isExtracting && (
          <div style={{ color: 'var(--accent-primary)', display: 'flex', gap: '0.5rem', alignItems: 'center' }} className="animate-pulse">
            <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            Processing...
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
