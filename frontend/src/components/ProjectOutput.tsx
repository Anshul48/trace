import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function ProjectOutput() {
  const { id } = useParams();
  const [files, setFiles] = useState<{name: string, content: string}[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [status, setStatus] = useState('fetching');

  const fetchOutput = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${id}/output`);
      const data = await res.json();
      if (data.files && data.files.length > 0) {
        setFiles(data.files);
        if (!selectedFile) setSelectedFile(data.files[0].name);
        setStatus('done');
      } else {
        // If files aren't there yet, the writer might still be running
        setStatus('writing');
      }
    } catch (e) {
      console.error(e);
      setStatus('error');
    }
  };

  useEffect(() => {
    fetchOutput();
    
    // Poll for updates in case the writer is still running
    const interval = setInterval(() => {
      fetchOutput();
    }, 3000);
    
    return () => clearInterval(interval);
  }, [id, selectedFile]);

  return (
    <div className="animate-fade-in flex gap-6" style={{ height: 'calc(100vh - 120px)' }}>
      {/* Left Panel: File Explorer */}
      <div className="w-64 flex flex-col" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
        <div className="p-4" style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
          [ OUTPUT FILES ]
        </div>
        
        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
          {status === 'writing' && (
            <div style={{ color: 'var(--accent-primary)', fontSize: '0.875rem', padding: '0.5rem' }} className="animate-pulse">
              &gt; WriterAgent working...
            </div>
          )}
          
          {files.map(file => (
            <button 
              key={file.name}
              onClick={() => setSelectedFile(file.name)}
              style={{
                textAlign: 'left',
                padding: '0.5rem',
                background: selectedFile === file.name ? 'var(--bg-tertiary)' : 'transparent',
                color: selectedFile === file.name ? 'var(--accent-primary)' : 'var(--text-primary)',
                border: 'none',
                cursor: 'pointer',
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}
            >
              {file.name}
            </button>
          ))}
        </div>
      </div>

      {/* Right Panel: File Viewer */}
      <div className="flex-1 flex flex-col" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
        <div className="p-4" style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
          {selectedFile ? `~/pipeline/${id?.split('-')[0]}/output/${selectedFile}` : '[ NO FILE SELECTED ]'}
        </div>
        
        <div className="flex-1 p-4 overflow-y-auto">
          {selectedFile && files.find(f => f.name === selectedFile) ? (
            <pre style={{ 
              whiteSpace: 'pre-wrap', 
              wordWrap: 'break-word', 
              color: 'var(--text-primary)', 
              fontFamily: 'monospace',
              fontSize: '14px',
              margin: 0
            }}>
              {files.find(f => f.name === selectedFile)?.content}
            </pre>
          ) : (
            <div style={{ color: 'var(--text-muted)' }}>
              &gt; Select a file to view its contents.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
