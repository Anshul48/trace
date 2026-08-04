import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function TraceEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [traces, setTraces] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ concept: '', type: '', relations: '' });

  useEffect(() => {
    fetch(`${API_BASE}/api/projects/${id}/traces`)
      .then(res => res.json())
      .then(data => {
        // Map the backend DB rows to our frontend format
        const mapped = data.map((t: any) => {
          // Check for user-overrides in the DB, otherwise use the extracted details
          const details = t.details || {};
          
          let relationsStr = '';
          if (details.relations && Array.isArray(details.relations)) {
            relationsStr = details.relations.map((r: any) => `${r.relation_type} -> ${r.target_concept}`).join(', ');
          }

          return {
            id: t.trace_id,
            concept: t.user_concept || details.anchor_concept || 'Unknown',
            type: t.user_type || details.artifact_type || 'Unknown',
            relations: t.user_relations || relationsStr || 'None'
          };
        });
        setTraces(mapped);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [id]);

  const startEdit = (trace: any) => {
    setEditingId(trace.id);
    setEditForm({ concept: trace.concept, type: trace.type, relations: trace.relations });
  };

  const saveEdit = () => {
    // Ideally this would send a PUT request to update user_concept, etc. in the DB.
    // For now, we update local state.
    setTraces(traces.map(t => t.id === editingId ? { ...t, ...editForm } : t));
    setEditingId(null);
  };

  const proceedToToc = () => {
    navigate(`/project/${id}/toc`);
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <div className="flex items-center justify-between">
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: '600', color: 'var(--text-primary)' }}>Trace Review</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Review and edit extracted concepts and relations.</p>
        </div>
        <button className="btn btn-primary" onClick={proceedToToc} disabled={loading}>
          Proceed to TOC Planner
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
        </button>
      </div>

      <div className="glass-panel" style={{ overflowX: 'auto', padding: '1.5rem' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Concept</th>
              <th>Type</th>
              <th>Relations</th>
              <th style={{ textAlign: 'right', width: '150px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem' }}>
                    <svg className="animate-spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                    Fetching traces...
                  </div>
                </td>
              </tr>
            )}
            {!loading && traces.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No traces found for this project.
                </td>
              </tr>
            )}
            {traces.map(trace => (
              <tr key={trace.id}>
                <td style={{ fontFamily: 'monospace', color: 'var(--text-muted)', fontSize: '0.85rem' }}>{trace.id.substring(0, 6)}</td>
                
                {editingId === trace.id ? (
                  <>
                    <td style={{ padding: '1rem' }}>
                      <input className="input-field" value={editForm.concept} onChange={e => setEditForm({...editForm, concept: e.target.value})} />
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <input className="input-field" value={editForm.type} onChange={e => setEditForm({...editForm, type: e.target.value})} />
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <input className="input-field" value={editForm.relations} onChange={e => setEditForm({...editForm, relations: e.target.value})} />
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button className="btn btn-primary" onClick={saveEdit} style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>Save</button>
                        <button className="btn btn-secondary" onClick={() => setEditingId(null)} style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>Cancel</button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td style={{ color: 'var(--text-primary)', fontWeight: '600' }}>{trace.concept}</td>
                    <td>
                      <span className="badge">{trace.type}</span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>{trace.relations}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-secondary" onClick={() => startEdit(trace)} style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                        Edit
                      </button>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
