import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type ThreadConfig = {
  id: string;
  type: 'paste' | 'upload';
  text: string;
  files: FileList | null;
  isChronological: boolean;
};

export function ProjectDashboard() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<any[]>([]);
  const [newProjectName, setNewProjectName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [threads, setThreads] = useState<ThreadConfig[]>([
    { id: `t_${Date.now()}`, type: 'paste', text: '', files: null, isChronological: false }
  ]);
  const [mergeProjectIds, setMergeProjectIds] = useState<string[]>([]);

  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      const data = await res.json();
      setProjects(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const updateThread = (id: string, updates: Partial<ThreadConfig>) => {
    setThreads(prev => prev.map(t => t.id === id ? { ...t, ...updates } : t));
  };

  const addThread = () => {
    setThreads(prev => [...prev, {
      id: `t_${Date.now()}`,
      type: 'paste',
      text: '',
      files: null,
      isChronological: false
    }]);
  };

  const removeThread = (id: string) => {
    setThreads(prev => prev.filter(t => t.id !== id));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    
    // Validation
    const hasData = threads.some(t => t.type === 'paste' ? t.text.trim() : (t.files && t.files.length > 0));
    if (!hasData && mergeProjectIds.length === 0) return;
    
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName })
      });
      const data = await res.json();
      
      const formData = new FormData();
      
      const threadsMeta = threads.map(t => ({ id: t.id, is_chronological: t.isChronological }));
      formData.append('threads', JSON.stringify(threadsMeta));
      formData.append('merge_project_ids', JSON.stringify(mergeProjectIds));
      
      threads.forEach(t => {
        if (t.type === 'paste' && t.text.trim()) {
          formData.append(`thread_${t.id}_text`, t.text);
        } else if (t.type === 'upload' && t.files) {
          for (let i = 0; i < t.files.length; i++) {
            formData.append(`thread_${t.id}_files`, t.files[i]);
          }
        }
      });
      
      await fetch(`${API_BASE}/api/projects/${data.id}/ingest_threads`, {
        method: 'POST',
        body: formData
      });
      
      navigate(`/project/${data.id}/ingest`);
    } catch (e) {
      console.error(e);
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this project?')) return;
    try {
      await fetch(`${API_BASE}/api/projects/${id}`, { method: 'DELETE' });
      fetchProjects();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* Create Project Section */}
      <div className="glass-panel" style={{ padding: '2rem' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: '600', marginBottom: '1.5rem', color: 'var(--text-primary)' }}>Create New Project</h2>
        
        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontWeight: '500', color: 'var(--text-secondary)' }}>Project Name</label>
            <input 
               type="text" 
               placeholder="E.g., Architecture Overview" 
               className="input-field"
               value={newProjectName}
               onChange={(e) => setNewProjectName(e.target.value)}
               disabled={isSubmitting}
               required
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontWeight: '500', color: 'var(--text-secondary)' }}>Merge Existing Workspaces</label>
            <select 
               multiple
               className="input-field"
               value={mergeProjectIds}
               onChange={(e) => {
                 const opts = Array.from(e.target.selectedOptions, option => option.value);
                 setMergeProjectIds(opts);
               }}
               style={{ minHeight: '100px' }}
            >
               {projects.map(p => (
                 <option key={p.id} value={p.id} style={{ padding: '0.3rem' }}>
                   {p.name} ({new Date(p.created_at).toLocaleDateString()})
                 </option>
               ))}
            </select>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Select past projects to merge their knowledge traces into this new project.</p>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
             <h3 style={{ fontSize: '1.2rem', fontWeight: '500', color: 'var(--text-primary)' }}>Knowledge Threads</h3>
             <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
               <strong>Map-Reduce Extraction:</strong> Add independent document threads to build a unified graph. Threads are extracted sequentially with isolated memory to prevent cross-contamination of ideas, then automatically clustered during synthesis.
             </p>
             
             <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
               {threads.map((t, index) => (
                  <div key={t.id} style={{ 
                    background: 'var(--bg-secondary)', 
                    padding: '1.5rem', 
                    borderRadius: '8px', 
                    border: '1px solid var(--border-color)', 
                    display: 'flex', 
                    flexDirection: 'column', 
                    gap: '1rem' 
                  }}>
                     <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                       <div style={{ fontWeight: '600', color: 'var(--text-primary)' }}>Thread {index + 1}</div>
                       <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                         <button 
                           type="button" 
                           onClick={() => updateThread(t.id, { type: 'upload' })} 
                           className="btn" 
                           style={{ 
                             padding: '0.3rem 0.8rem', 
                             fontSize: '0.8rem',
                             background: t.type === 'upload' ? 'var(--accent-primary)' : 'transparent',
                             color: t.type === 'upload' ? 'white' : 'var(--text-secondary)',
                             border: '1px solid',
                             borderColor: t.type === 'upload' ? 'var(--accent-primary)' : 'var(--border-color)'
                           }}
                         >
                           Upload Files
                         </button>
                         <button 
                           type="button" 
                           onClick={() => updateThread(t.id, { type: 'paste' })} 
                           className="btn" 
                           style={{ 
                             padding: '0.3rem 0.8rem', 
                             fontSize: '0.8rem',
                             background: t.type === 'paste' ? 'var(--accent-primary)' : 'transparent',
                             color: t.type === 'paste' ? 'white' : 'var(--text-secondary)',
                             border: '1px solid',
                             borderColor: t.type === 'paste' ? 'var(--accent-primary)' : 'var(--border-color)'
                           }}
                         >
                           Paste Text
                         </button>
                         {threads.length > 1 && (
                           <button 
                             type="button" 
                             onClick={() => removeThread(t.id)} 
                             style={{ 
                               color: 'var(--error)', 
                               background: 'transparent', 
                               border: 'none', 
                               cursor: 'pointer', 
                               marginLeft: '0.5rem',
                               fontSize: '1.2rem',
                               opacity: '0.7'
                             }}
                             title="Remove Thread"
                           >
                             ✕
                           </button>
                         )}
                       </div>
                     </div>
                     
                     {t.type === 'paste' ? (
                       <textarea
                         className="input-field"
                         placeholder="Paste your document content here..."
                         value={t.text}
                         onChange={(e) => updateThread(t.id, { text: e.target.value })}
                         disabled={isSubmitting}
                         style={{ minHeight: '120px', resize: 'vertical' }}
                       />
                     ) : (
                       <input 
                         type="file" 
                         multiple 
                         accept=".txt,.md"
                         className="input-field"
                         onChange={(e) => updateThread(t.id, { files: e.target.files })}
                         disabled={isSubmitting}
                         style={{ padding: '0.6rem 1rem' }}
                       />
                     )}
                     
                     <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                       <input 
                         type="checkbox" 
                         checked={t.isChronological} 
                         onChange={(e) => updateThread(t.id, { isChronological: e.target.checked })} 
                         style={{ cursor: 'pointer' }}
                       />
                       Strictly chronological sequence (oldest to newest)
                     </label>
                  </div>
               ))}
             </div>
             
             <button 
               type="button" 
               onClick={addThread} 
               className="btn btn-secondary" 
               style={{ 
                 alignSelf: 'flex-start', 
                 borderStyle: 'dashed', 
                 borderColor: 'var(--text-muted)',
                 padding: '0.75rem 1.5rem',
                 marginTop: '0.5rem'
               }}
             >
               ➕ Add Knowledge Thread
             </button>
          </div>

          <button type="submit" className="btn btn-primary" disabled={isSubmitting} style={{ alignSelf: 'flex-end', padding: '0.75rem 2rem', fontSize: '1rem', marginTop: '1rem' }}>
            {isSubmitting ? (
              <>
                <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'spin 1s linear infinite', marginRight: '0.5rem' }}><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                Initializing Workspace...
              </>
            ) : (
              <>
                Create & Ingest
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: '0.5rem' }}><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              </>
            )}
          </button>
        </form>
      </div>

      {/* Projects List */}
      <div className="glass-panel" style={{ padding: '2rem', overflowX: 'auto' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: '600', marginBottom: '1.5rem', color: 'var(--text-primary)' }}>Your Workspaces</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Project Name</th>
              <th>Status</th>
              <th>Created</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {projects.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                  No projects found. Create one above to get started.
                </td>
              </tr>
            )}
            {projects.map(project => (
              <tr key={project.id}>
                <td style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>{project.id.split('-')[0]}</td>
                <td style={{ fontWeight: '500' }}>{project.name}</td>
                <td>
                  <span className={`badge ${project.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>
                    {project.status}
                  </span>
                </td>
                <td style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>{new Date(project.created_at).toLocaleString()}</td>
                <td style={{ textAlign: 'right' }}>
                  <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                    <button 
                      className="btn btn-secondary" 
                      style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
                      onClick={() => navigate(`/project/${project.id}/traces`)}
                    >
                      Open
                    </button>
                    <button 
                      className="btn btn-secondary"
                      style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', color: 'var(--accent-primary)', borderColor: 'var(--accent-primary)' }}
                      onClick={async () => {
                        const targetId = prompt('Enter the Project ID of the workspace you want to merge into this one:');
                        if (targetId && targetId.trim()) {
                          try {
                            await fetch(`${API_BASE}/api/projects/${project.id}/merge`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ source_project_ids: [targetId.trim()] })
                            });
                            alert('Merge started successfully in the background!');
                            fetchProjects();
                          } catch (e) {
                            alert('Failed to start merge.');
                            console.error(e);
                          }
                        }
                      }}
                    >
                      Merge
                    </button>
                    <button 
                      className="btn btn-secondary"
                      style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', color: 'var(--error)', borderColor: 'rgba(239,68,68,0.3)' }}
                      onClick={() => handleDelete(project.id)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
