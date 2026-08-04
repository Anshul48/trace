import { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const MODEL_OPTIONS = [
  "gemini/gemini-3.1-flash-lite",
  "gemini/gemini-3.1-pro",
  "gemini/gemma-4-31b-it",
  "deepseek/deepseek-chat",
  "deepseek/deepseek-v4-flash",
  "deepseek/deepseek-v4-pro"
];

export function Settings() {
  const [deepseekKey, setDeepseekKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [plannerModel, setPlannerModel] = useState('gemini/gemini-3.1-flash-lite');
  const [writerModel, setWriterModel] = useState('gemini/gemma-4-31b-it');
  
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
  
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
      
      localStorage.setItem('theme', theme);
      if (theme === 'light') {
        document.documentElement.classList.add('theme-light');
      } else {
        document.documentElement.classList.remove('theme-light');
      }
      
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
    <div className="animate-fade-in max-w-3xl mx-auto" style={{ display: 'flex', flexDirection: 'column', gap: '2rem', padding: '2rem 0' }}>
      <div>
        <h1 style={{ fontSize: '1.75rem', fontWeight: '600', color: 'var(--text-primary)' }}>Settings</h1>
        <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Configure API keys and model preferences.</p>
      </div>

      <form onSubmit={handleSave} className="glass-panel" style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg>
            API Keys
          </h2>
          <div className="flex flex-col gap-4">
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '500' }}>Google Gemini</label>
              <input 
                type="password"
                className="input-field"
                placeholder="AIzaSy..."
                value={geminiKey}
                onChange={e => setGeminiKey(e.target.value)}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '500' }}>DeepSeek</label>
              <input 
                type="password"
                className="input-field"
                placeholder="sk-..."
                value={deepseekKey}
                onChange={e => setDeepseekKey(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div style={{ height: '1px', background: 'var(--border-color)' }}></div>

        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"></path><line x1="16" y1="8" x2="2" y2="22"></line><line x1="17.5" y1="15" x2="9" y2="15"></line></svg>
            Model Configuration
          </h2>
          <div className="flex flex-col gap-4">
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '500' }}>Planner Model</label>
              <select className="input-field" value={plannerModel} onChange={e => setPlannerModel(e.target.value)}>
                {MODEL_OPTIONS.map(model => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.5rem' }}>Used for analyzing traces and structuring the Table of Contents.</p>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '500' }}>Writer Model</label>
              <select className="input-field" value={writerModel} onChange={e => setWriterModel(e.target.value)}>
                {MODEL_OPTIONS.map(model => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.5rem' }}>Used for generating the final comprehensive content based on the TOC.</p>
            </div>
          </div>
        </div>
        
        <div style={{ height: '1px', background: 'var(--border-color)' }}></div>

        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
            Appearance
          </h2>
          <div className="flex flex-col gap-4">
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '500' }}>Theme</label>
              <select className="input-field" value={theme} onChange={e => setTheme(e.target.value)}>
                <option value="dark">Obsidian Dark (Default)</option>
                <option value="light">Obsidian Light</option>
              </select>
            </div>
          </div>
        </div>
        
        <div className="flex items-center justify-end gap-4 mt-2">
          {saveSuccess && (
            <span style={{ color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
              Settings Saved
            </span>
          )}
          <button type="submit" className="btn btn-primary" disabled={isSaving} style={{ padding: '0.75rem 2rem' }}>
            {isSaving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </form>
    </div>
  );
}
