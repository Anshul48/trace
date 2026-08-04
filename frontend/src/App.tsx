import { BrowserRouter as Router, Routes, Route, Link, useLocation, Outlet } from 'react-router-dom';
import { ProjectDashboard } from './components/ProjectDashboard';
import { PipelineLiveView } from './components/PipelineLiveView';
import { TraceEditor } from './components/TraceEditor';
import { TOCReviewer } from './components/TOCReviewer';
import { ProjectOutput } from './components/ProjectOutput';
import { Settings } from './components/Settings';
import './index.css';

function Navbar() {
  return (
    <nav className="glass-panel" style={{ padding: '1rem 0', margin: '1rem auto', maxWidth: '1200px', borderRadius: '16px' }}>
      <div className="container flex items-center justify-between" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link to="/" style={{ color: 'var(--text-primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ background: 'var(--accent-gradient)', padding: '0.5rem', borderRadius: '8px', display: 'flex' }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: '600', letterSpacing: '0.05em' }}>TRACE OS</span>
        </Link>
        <div style={{ display: 'flex', gap: '1.5rem' }}>
          <Link to="/" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: '500', transition: 'color 0.2s' }} onMouseOver={e => e.currentTarget.style.color = 'var(--accent-primary)'} onMouseOut={e => e.currentTarget.style.color = 'var(--text-secondary)'}>Projects</Link>
          <Link to="/settings" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontWeight: '500', transition: 'color 0.2s' }} onMouseOver={e => e.currentTarget.style.color = 'var(--accent-primary)'} onMouseOut={e => e.currentTarget.style.color = 'var(--text-secondary)'}>Settings</Link>
        </div>
      </div>
    </nav>
  );
}

function ProjectLayout() {
  const location = useLocation();
  const pathParts = location.pathname.split('/');
  const projectId = pathParts[2];
  const activeTab = pathParts[3] || 'traces';

  const tabs = [
    { id: 'ingest', label: '1. Ingest' },
    { id: 'traces', label: '2. Traces' },
    { id: 'toc', label: '3. TOC' },
    { id: 'output', label: '4. Output' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', height: '100%' }}>
      <div className="glass-panel" style={{ display: 'flex', padding: '0.5rem', gap: '0.5rem', borderRadius: '12px' }}>
        {tabs.map(tab => (
          <Link 
            key={tab.id}
            to={`/project/${projectId}/${tab.id}`}
            style={{
              padding: '0.5rem 1.5rem',
              borderRadius: '8px',
              textDecoration: 'none',
              color: activeTab === tab.id ? 'white' : 'var(--text-secondary)',
              background: activeTab === tab.id ? 'var(--accent-gradient)' : 'transparent',
              fontWeight: activeTab === tab.id ? '600' : '500',
              transition: 'all 0.3s ease'
            }}
          >
            {tab.label}
          </Link>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <Outlet />
      </div>
    </div>
  );
}

function App() {
  return (
    <Router>
      <Navbar />
      <main className="container pb-8" style={{ minHeight: 'calc(100vh - 120px)' }}>
        <Routes>
          <Route path="/" element={<ProjectDashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/project/:id" element={<ProjectLayout />}>
            <Route path="ingest" element={<PipelineLiveView />} />
            <Route path="traces" element={<TraceEditor />} />
            <Route path="toc" element={<TOCReviewer />} />
            <Route path="output" element={<ProjectOutput />} />
          </Route>
        </Routes>
      </main>
    </Router>
  );
}

export default App;
