import { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function Settings() {
  const [deepseekKey, setDeepseekKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [plannerModel, setPlannerModel] = useState('gemini/gemini-3.1-flash-lite');
  const [writerModel, setWriterModel] = useState('gemini/gemma-4-31b-it');
  
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/settings`)
      .then(res => res.json())
      .then(data => {
        setDeepseekKey(data.deepseek_api_key || '');
        setGeminiKey(data.gemini_api_key || '');
        setPlannerModel(data.planner_model || 'gemini/gemini-3.1-flash-lite');
        setWriterModel(data.writer_model || 'gemini/gemma-4-31b-it');
        setIsLoading(false);
      })
      .catch(err => {
        console.error("Failed to load settings:", err);
        setIsLoading(false);
      });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccess(false);
    
    try {
      await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deepseek_api_key: deepseekKey,
          gemini_api_key: geminiKey,
          planner_model: plannerModel,
          writer_model: writerModel
        })
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error("Failed to save settings", err);
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) return <div style={{ color: 'var(--text-muted)' }}>&gt; loading...</div>;

  return (
    <div className="animate-fade-in max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--accent-primary)' }}>~/config/env</h1>
      </div>

      <form onSubmit={handleSave} className="flex flex-col gap-6" style={{ background: 'var(--bg-secondary)', padding: '1.5rem', border: '1px solid var(--border-color)' }}>
        <div>
          <div style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}># API KEYS</div>
          <div className="flex flex-col gap-4">
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>GEMINI_API_KEY=</label>
              <input 
                type="password"
                className="input-field"
                placeholder="..."
                value={geminiKey}
                onChange={e => setGeminiKey(e.target.value)}
                style={{ background: 'var(--bg-primary)' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>DEEPSEEK_API_KEY=</label>
              <input 
                type="password"
                className="input-field"
                placeholder="..."
                value={deepseekKey}
                onChange={e => setDeepseekKey(e.target.value)}
                style={{ background: 'var(--bg-primary)' }}
              />
            </div>
          </div>
        </div>

        <div style={{ height: '1px', background: 'var(--border-color)', margin: '1rem 0' }}></div>

        <div>
          <div style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}># MODEL DEFAULTS</div>
          <div className="flex flex-col gap-4">
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>PLANNER_MODEL=</label>
              <select className="input-field" value={plannerModel} onChange={e => setPlannerModel(e.target.value)} style={{ background: 'var(--bg-primary)' }}>
                <option value="gemini/gemini-3.1-flash-lite">gemini/gemini-3.1-flash-lite</option>
                <option value="gemini/gemini-3.1-pro">gemini/gemini-3.1-pro</option>
                <option value="deepseek/deepseek-chat">deepseek/deepseek-chat</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>WRITER_MODEL=</label>
              <select className="input-field" value={writerModel} onChange={e => setWriterModel(e.target.value)} style={{ background: 'var(--bg-primary)' }}>
                <option value="gemini/gemma-4-31b-it">gemini/gemma-4-31b-it</option>
                <option value="gemini/gemini-3.1-pro">gemini/gemini-3.1-pro</option>
              </select>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-4 mt-4">
          <button type="submit" className="btn btn-primary" disabled={isSaving}>
            {isSaving ? '[ SAVING... ]' : '[ WRITE TO .ENV ]'}
          </button>
          
          {saveSuccess && (
            <span style={{ color: 'var(--success)' }}>
              OK
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
