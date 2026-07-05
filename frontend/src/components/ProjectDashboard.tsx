import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function ProjectDashboard() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<any[]>([]);
  const [newProjectName, setNewProjectName] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim() || !selectedFiles || selectedFiles.length === 0) return;
    
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName })
      });
      const data = await res.json();
      
      const formData = new FormData();
      for (let i = 0; i < selectedFiles.length; i++) {
        formData.append('files', selectedFiles[i]);
      }
      
      await fetch(`${API_BASE}/api/projects/${data.id}/ingest`, {
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
    if (!confirm('rm -rf project?')) return;
    try {
      await fetch(`${API_BASE}/api/projects/${id}`, { method: 'DELETE' });
      fetchProjects();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--accent-primary)' }}>~/projects</h1>
      </div>

      <div style={{ marginBottom: '2rem', padding: '1rem', border: '1px solid var(--border-color)', background: 'var(--bg-secondary)' }}>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>$ mkdir new_project && upload_docs</p>
        <form onSubmit={handleCreate} className="flex flex-col gap-4">
          <input 
            type="text" 
            placeholder="Project Name..." 
            className="input-field"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            disabled={isSubmitting}
            style={{ background: 'var(--bg-primary)' }}
          />
          <input 
            type="file" 
            multiple 
            className="input-field"
            onChange={(e) => setSelectedFiles(e.target.files)}
            disabled={isSubmitting}
            style={{ background: 'var(--bg-primary)' }}
          />
          <div>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
              {isSubmitting ? '[ RUNNING... ]' : '[ EXECUTE INGESTION ]'}
            </button>
          </div>
        </form>
      </div>

      <div style={{ border: '1px solid var(--border-color)' }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>NAME</th>
              <th>STATUS</th>
              <th>CREATED</th>
              <th>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {projects.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                  No directories found.
                </td>
              </tr>
            )}
            {projects.map(project => (
              <tr key={project.id}>
                <td style={{ fontFamily: 'monospace', color: 'var(--text-muted)' }}>{project.id.split('-')[0]}</td>
                <td style={{ color: 'var(--text-primary)' }}>{project.name}</td>
                <td>
                  <span className={`badge ${project.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>
                    {project.status}
                  </span>
                </td>
                <td style={{ color: 'var(--text-secondary)' }}>{new Date(project.created_at).toLocaleString()}</td>
                <td>
                  <div className="flex gap-4">
                    <button 
                      className="btn btn-secondary" 
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                      onClick={() => navigate(`/project/${project.id}/traces`)}
                    >
                      [VIEW]
                    </button>
                    <button 
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', color: 'var(--error)', borderColor: 'var(--error)' }}
                      onClick={() => handleDelete(project.id)}
                    >
                      [RM]
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
