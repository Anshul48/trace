import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import ForceGraph3D from 'react-force-graph-3d';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function ProjectOutput() {
  const { id } = useParams();
  const [files, setFiles] = useState<{name: string, content: string}[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedCanvas, setSelectedCanvas] = useState<string | null>(null);
  const [status, setStatus] = useState('fetching');
  const [activeTab, setActiveTab] = useState<'files' | '3d'>('files');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(288); // Default w-72 is 288px
  const [isResizing, setIsResizing] = useState(false);
  const fgRef = useRef<any>();
  
  // Progress tracking
  const [tocLines, setTocLines] = useState<string[]>([]);
  const [writingStatus, setWritingStatus] = useState<Record<string, 'writing' | 'done'>>({});
  const [filter, setFilter] = useState('');
  
  // Notification
  const [notification, setNotification] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3000);
  };

  const fetchOutput = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${id}/output`);
      const data = await res.json();
      if (data.files && data.files.length > 0) {
        setFiles(data.files);
        if (!selectedFile) setSelectedFile(data.files[0].name);
        setStatus('done');
      } else {
        setStatus('writing');
      }
    } catch (e) {
      console.error(e);
      setStatus('error');
    }
  };

  useEffect(() => {
    fetchOutput();
    
    // Fetch TOC for progress tracking
    fetch(`${API_BASE}/api/projects/${id}/toc`)
      .then(res => res.json())
      .then(data => {
        if (data.toc) {
          setTocLines(data.toc.split('\n'));
        }
      });
      
    // Connect WebSocket
    const wsBase = API_BASE.replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsBase}/api/ws/logs/${id}`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'DocumentWritingStarted') {
          setWritingStatus(prev => ({ ...prev, [data.payload.name]: 'writing' }));
        } else if (data.type === 'DocumentWritten') {
          setWritingStatus(prev => ({ ...prev, [data.payload.name]: 'done' }));
          fetchOutput();
        } else if (data.type === 'WriterCompleted') {
          setStatus('done');
          fetchOutput();
        }
      } catch (e) {
        console.error('Failed to parse WS message', e);
      }
    };
    
    const interval = setInterval(() => {
      if (status === 'writing') fetchOutput();
    }, 3000);
    
    return () => {
      clearInterval(interval);
      ws.close();
    };
  }, [id, status, selectedFile]);

  // Resizing logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      
      // Calculate new width, min 200px, max 50% of screen
      let newWidth = e.clientX - 32; // Rough offset from left edge
      if (newWidth < 200) newWidth = 200;
      if (newWidth > window.innerWidth / 2) newWidth = window.innerWidth / 2;
      
      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none'; // Prevent text selection while dragging
    } else {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  const handleRegenerateCanvas = async () => {
    try {
      await fetch(`${API_BASE}/api/projects/${id}/canvas/regenerate`, { method: 'POST' });
      fetchOutput();
      showNotification('Canvas regeneration complete');
    } catch (e) {
      alert('Error regenerating canvas');
    }
  };

  const handleRegenerateDoc = async () => {
    try {
      await fetch(`${API_BASE}/api/projects/${id}/consolidate/regenerate`, { method: 'POST' });
      fetchOutput();
      showNotification('Document regeneration complete');
    } catch (e) {
      alert('Error regenerating document');
    }
  };

  // Check if writing is done
  const isWritingDone = status === 'done';

  return (
    <div className="animate-fade-in flex flex-col" style={{ height: 'calc(100vh - 120px)', minHeight: '600px', position: 'relative' }}>
      
      {/* Top View Toggle */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button 
          className="btn"
          onClick={() => setActiveTab('files')}
          style={{ 
            background: activeTab === 'files' ? 'var(--accent-primary)' : 'var(--bg-secondary)',
            color: activeTab === 'files' ? 'white' : 'var(--text-secondary)',
            border: '1px solid var(--border-color)',
            padding: '0.5rem 1.5rem',
            borderRadius: '8px',
            fontSize: '0.9rem',
            fontWeight: '600'
          }}
        >
          Document View
        </button>
        <button 
          className="btn"
          onClick={() => setActiveTab('3d')}
          style={{ 
            background: activeTab === '3d' ? 'var(--accent-primary)' : 'var(--bg-secondary)',
            color: activeTab === '3d' ? 'white' : 'var(--text-secondary)',
            border: '1px solid var(--border-color)',
            padding: '0.5rem 1.5rem',
            borderRadius: '8px',
            fontSize: '0.9rem',
            fontWeight: '600'
          }}
        >
          3D Canvas
        </button>
      </div>

      {activeTab === 'files' && (
        <div style={{ display: 'flex', flexDirection: 'row', gap: '1rem', flex: 1, overflow: 'hidden' }}>
          
          {/* Obsidian-Style Sidebar (TOC) */}
          {sidebarOpen && (
            <div className="glass-panel flex flex-col" style={{ width: `${sidebarWidth}px`, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <span style={{ color: 'var(--text-primary)', fontWeight: '600', fontSize: '1.1rem' }}>Table of Contents</span>
                <input 
                  type="text"
                  placeholder="Filter concepts..."
                  className="input-field"
                  style={{ padding: '0.5rem', fontSize: '0.85rem' }}
                  value={filter}
                  onChange={e => setFilter(e.target.value)}
                />
              </div>
              
              <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                {status === 'writing' && (
                  <div style={{ color: 'var(--accent-secondary)', fontSize: '0.85rem', padding: '0.5rem', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '6px', marginBottom: '1rem' }} className="animate-pulse">
                    Writer is generating content...
                  </div>
                )}
                
                {tocLines.map((line, i) => {
                  const trimmed = line.trim();
                  if (!trimmed) return null;
                  
                  if (trimmed.startsWith('#')) {
                    const level = trimmed.match(/^#+/)?.[0].length || 1;
                    const text = trimmed.replace(/^#+\s*/, '');
                    if (filter && !text.toLowerCase().includes(filter.toLowerCase())) return null;
                    const size = level === 1 ? '1rem' : level === 2 ? '0.9rem' : '0.85rem';
                    const weight = level === 1 ? '600' : '500';
                    const color = level === 1 ? 'var(--text-primary)' : 'var(--text-secondary)';
                    return (
                      <div key={i} style={{ fontSize: size, fontWeight: weight, color, marginTop: '1rem', marginBottom: '0.25rem' }}>
                        {text}
                      </div>
                    );
                  }
                  
                  if (trimmed.startsWith('* [[')) {
                    const entityName = trimmed.substring(4, trimmed.length - 2);
                    if (filter && !entityName.toLowerCase().includes(filter.toLowerCase())) return null;
                    
                    const stat = writingStatus[entityName];
                    const fileName = `${entityName}.md`;
                    const fileObj = files.find(f => f.name === fileName || f.name.endsWith(`/${fileName}`) || f.name.endsWith(`\\${fileName}`));
                    const isFileAvailable = !!fileObj;
                    const fullFilePath = fileObj ? fileObj.name : fileName;
                    const isSelected = selectedFile === fullFilePath;
                    
                    let style: React.CSSProperties = {
                      padding: '0.4rem 0.75rem',
                      borderRadius: '6px',
                      cursor: isFileAvailable ? 'pointer' : 'default',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.85rem',
                      background: isSelected ? 'var(--bg-tertiary)' : 'transparent',
                      color: isSelected ? 'var(--accent-primary)' : (isFileAvailable ? 'var(--text-primary)' : 'var(--text-muted)'),
                      transition: 'all 0.2s',
                      borderLeft: isSelected ? '3px solid var(--accent-primary)' : '3px solid transparent'
                    };
                    
                    let icon = <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--text-muted)' }} />;
                    
                    if (stat === 'writing') {
                      style.background = 'rgba(59, 130, 246, 0.1)';
                      style.color = 'var(--accent-secondary)';
                      style.borderLeftColor = 'var(--accent-secondary)';
                      icon = <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-secondary)' }} className="animate-pulse" />;
                    } else if (stat === 'done' || isFileAvailable) {
                      icon = <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--success)' }}><path d="M20 6L9 17l-5-5"/></svg>;
                    }
                    
                    return (
                      <div 
                        key={i} 
                        style={style}
                        onClick={() => {
                          if (isFileAvailable) setSelectedFile(fullFilePath);
                        }}
                        onMouseEnter={(e) => {
                          if (isFileAvailable && !isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) e.currentTarget.style.background = 'transparent';
                        }}
                      >
                        {icon}
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entityName}</span>
                      </div>
                    );
                  }
                  return null;
                })}
              </div>
            </div>
          )}

          {/* Draggable Resizer Handle */}
          {sidebarOpen && (
            <div 
              onMouseDown={() => setIsResizing(true)}
              style={{
                width: '6px',
                cursor: 'col-resize',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: isResizing ? 'var(--accent-primary)' : 'transparent',
                borderRadius: '3px',
                transition: 'background 0.2s ease',
                flexShrink: 0
              }}
              onMouseEnter={(e) => {
                if (!isResizing) e.currentTarget.style.background = 'rgba(255,255,255,0.1)';
              }}
              onMouseLeave={(e) => {
                if (!isResizing) e.currentTarget.style.background = 'transparent';
              }}
            >
              <div style={{ width: '2px', height: '30px', background: 'var(--border-color)', borderRadius: '2px' }} />
            </div>
          )}

          {/* Main Obsidian Document View */}
          <div className="glass-panel flex-1 flex flex-col" style={{ overflow: 'hidden', minWidth: '300px' }}>
            <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <button 
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', padding: '0.25rem' }}
                  title="Toggle Sidebar"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line></svg>
                </button>
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                  {selectedFile ? selectedFile : 'No file selected'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-secondary" style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }} onClick={handleRegenerateCanvas}>
                  Regenerate 2D Canvas
                </button>
                <button className="btn btn-secondary" style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }} onClick={handleRegenerateDoc}>
                  Regenerate Consolidated Doc
                </button>
              </div>
            </div>
            
            <div style={{ flex: 1, padding: '2rem 3rem', overflowY: 'auto', background: 'var(--bg-primary)' }}>
              {status === 'writing' && (!files || files.length === 0) ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
                  <div className="flex flex-col items-center gap-4">
                    <svg className="animate-spin" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                    <span>Generating Documents...</span>
                  </div>
                </div>
              ) : (
                selectedFile && files.find(f => f.name === selectedFile) ? (
                  <div className="markdown-preview" style={{ maxWidth: '800px', margin: '0 auto', color: 'var(--text-primary)', lineHeight: '1.7', fontSize: '1rem' }}>
                    {selectedFile.endsWith('.md') ? (
                       <ReactMarkdown remarkPlugins={[remarkGfm]}>
                         {files.find(f => f.name === selectedFile)?.content || ''}
                       </ReactMarkdown>
                    ) : (
                      <pre style={{ 
                        whiteSpace: 'pre-wrap', 
                        wordWrap: 'break-word', 
                        color: 'var(--text-primary)', 
                        fontFamily: 'monospace',
                        fontSize: '14px'
                      }}>
                        {files.find(f => f.name === selectedFile)?.content}
                      </pre>
                    )}
                  </div>
                ) : (
                  <div style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                    Select a document from the sidebar to read.
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      )}

      {/* Fullscreen 3D Canvas Mode */}
      {activeTab === '3d' && (
        <div className="glass-panel" style={{ flex: 1, position: 'relative', overflow: 'hidden', borderRadius: '12px' }}>
          
          {/* Floating Canvas Toolbar */}
          <div style={{ position: 'absolute', top: '1rem', right: '1rem', zIndex: 10, display: 'flex', gap: '0.75rem', background: 'rgba(0,0,0,0.5)', padding: '0.5rem', borderRadius: '8px', backdropFilter: 'blur(8px)' }}>
             {files.filter(f => f.name.endsWith('.canvas')).length > 0 && (
               <select 
                 className="input-field" 
                 style={{ padding: '0.2rem 0.5rem', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', borderRadius: '4px', fontSize: '0.8rem' }}
                 value={selectedCanvas || files.filter(f => f.name.endsWith('.canvas'))[0]?.name || ''}
                 onChange={(e) => setSelectedCanvas(e.target.value)}
               >
                 {files.filter(f => f.name.endsWith('.canvas')).map(f => (
                   <option key={f.name} value={f.name}>{f.name}</option>
                 ))}
               </select>
             )}
             <button className="btn btn-secondary" style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }} onClick={handleRegenerateCanvas}>
               Regenerate Graph
             </button>
             <span className="badge badge-success" style={{ alignSelf: 'center' }}>Interactive Mode</span>
          </div>

          {(() => {
            const canvasFiles = files.filter(f => f.name.endsWith('.canvas'));
            if (canvasFiles.length === 0) return <div style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>No canvas file found. Please regenerate the canvas.</div>;
            
            const canvasFile = selectedCanvas ? files.find(f => f.name === selectedCanvas) : canvasFiles[0];
            if (!canvasFile) return <div style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>Canvas file not found.</div>;
            
            let graphData = { nodes: [], links: [] };
            try {
              const data = JSON.parse(canvasFile.content);
              graphData.nodes = data.nodes.map((n: any) => ({
                id: n.id,
                name: n.file || n.text || n.id,
                val: 2,
                group: Math.floor(Math.random() * 5)
              }));
              
              const nodeIds = new Set(data.nodes.map((n: any) => n.id));
              
              // To prevent react-force-graph-3d from crashing when dagMode="lr" encounters a cycle,
              // we perform a simple DFS to break any cycles. We also MUST filter out edges that
              // point to non-existent nodes, which can happen if entities were filtered by the TOC.
              const adj = new Map();
              data.edges.forEach((e: any) => {
                if (nodeIds.has(e.fromNode) && nodeIds.has(e.toNode)) {
                  if (!adj.has(e.fromNode)) adj.set(e.fromNode, []);
                  adj.get(e.fromNode).push(e);
                }
              });
              
              const visiting = new Set();
              const visited = new Set();
              const validEdges: any[] = [];
              
              const dfs = (nodeId: string) => {
                visiting.add(nodeId);
                const edges = adj.get(nodeId) || [];
                for (const e of edges) {
                  if (visiting.has(e.toNode)) {
                    continue; // Back-edge detected, break the cycle
                  }
                  validEdges.push(e);
                  if (!visited.has(e.toNode)) {
                    dfs(e.toNode);
                  }
                }
                visiting.delete(nodeId);
                visited.add(nodeId);
              };
              
              data.nodes.forEach((n: any) => {
                if (!visited.has(n.id)) {
                  dfs(n.id);
                }
              });

              graphData.links = validEdges.map((e: any) => ({
                source: e.fromNode,
                target: e.toNode,
                name: e.label
              }));
            } catch (e) {
              return <div style={{ color: 'var(--error)', padding: '2rem' }}>Error parsing canvas data</div>;
            }

            return (
              <ForceGraph3D
                ref={fgRef}
                graphData={graphData}
                nodeLabel="name"
                nodeAutoColorBy="group"
                nodeRelSize={6}
                nodeOpacity={0.9}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                linkCurvature={0.2}
                linkWidth={1.5}
                linkColor={() => 'rgba(139, 92, 246, 0.4)'}
                linkDirectionalParticles={3}
                linkDirectionalParticleWidth={2.5}
                linkDirectionalParticleSpeed={0.005}
                linkDirectionalParticleColor={() => '#8b5cf6'}
                backgroundColor="var(--bg-primary)"
                dagMode="lr"
                dagLevelDistance={150}
                onEngineStop={() => {
                  if (fgRef.current) {
                    fgRef.current.zoomToFit(800, 50);
                  }
                }}
              />
            );
          })()}
        </div>
      )}

      {/* Notification Toast */}
      {notification && (
        <div style={{
          position: 'fixed',
          bottom: '2rem',
          right: '2rem',
          zIndex: 9999,
          background: 'var(--success, #10b981)',
          color: 'white',
          padding: '1rem 1.5rem',
          borderRadius: '8px',
          boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
          fontWeight: '500',
          animation: 'fade-in 0.3s ease-out'
        }}>
          {notification}
        </div>
      )}
    </div>
  );
}
