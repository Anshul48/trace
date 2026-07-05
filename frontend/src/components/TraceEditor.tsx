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

  const startGraphBuild = async () => {
    try {
      await fetch(`${API_BASE}/api/projects/${id}/synthesize`, { method: 'POST' });
      navigate(`/project/${id}/toc`);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 style={{ fontSize: '1.25rem', marginBottom: '0.5rem', color: 'var(--accent-primary)' }}>~/pipeline/{id?.split('-')[0]}/traces</h1>
        </div>
        <button className="btn btn-primary" onClick={startGraphBuild} disabled={loading}>
          [ BUILD GRAPH ]
        </button>
      </div>

      <div style={{ border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr>
              <th style={{ color: 'var(--text-secondary)' }}>ID</th>
              <th style={{ color: 'var(--text-secondary)' }}>CONCEPT</th>
              <th style={{ color: 'var(--text-secondary)' }}>TYPE</th>
              <th style={{ color: 'var(--text-secondary)' }}>RELATIONS</th>
              <th style={{ color: 'var(--text-secondary)', width: '150px' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  &gt; fetching traces...
                </td>
              </tr>
            )}
            {!loading && traces.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  &gt; no traces found.
                </td>
              </tr>
            )}
            {traces.map(trace => (
              <tr key={trace.id}>
                <td style={{ fontFamily: 'monospace', color: 'var(--text-muted)' }}>{trace.id.substring(0, 6)}</td>
                
                {editingId === trace.id ? (
                  <>
                    <td style={{ padding: '1rem' }}>
                      <input className="input-field" value={editForm.concept} onChange={e => setEditForm({...editForm, concept: e.target.value})} style={{ background: 'var(--bg-primary)' }} />
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <input className="input-field" value={editForm.type} onChange={e => setEditForm({...editForm, type: e.target.value})} style={{ background: 'var(--bg-primary)' }} />
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <input className="input-field" value={editForm.relations} onChange={e => setEditForm({...editForm, relations: e.target.value})} style={{ background: 'var(--bg-primary)' }} />
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <div className="flex gap-2">
                        <button className="btn btn-primary" onClick={saveEdit} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>[SAVE]</button>
                        <button className="btn btn-secondary" onClick={() => setEditingId(null)} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>[ESC]</button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td style={{ color: 'var(--accent-primary)', fontWeight: 'bold' }}>{trace.concept}</td>
                    <td>
                      <span className="badge" style={{ borderColor: 'var(--text-secondary)', color: 'var(--text-secondary)' }}>{trace.type}</span>
                    </td>
                    <td style={{ color: 'var(--text-primary)' }}>{trace.relations}</td>
                    <td>
                      <button className="btn btn-secondary" onClick={() => startEdit(trace)} style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                        [EDIT]
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
