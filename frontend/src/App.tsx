import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { ProjectDashboard } from './components/ProjectDashboard';
import { PipelineLiveView } from './components/PipelineLiveView';
import { TraceEditor } from './components/TraceEditor';
import { TOCReviewer } from './components/TOCReviewer';
import { ProjectOutput } from './components/ProjectOutput';
import { Settings } from './components/Settings';
import './index.css';

function Navbar() {
  return (
    <nav style={{ borderBottom: '1px solid var(--border-color)', padding: '1rem 0', background: 'var(--bg-secondary)' }}>
      <div className="container flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2" style={{ color: 'var(--accent-primary)', textDecoration: 'none' }}>
          <span style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>&gt;_ TRACE OS</span>
        </Link>
        <div className="flex gap-6">
          <Link to="/" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>[projects]</Link>
          <Link to="/settings" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>[settings]</Link>
        </div>
      </div>
    </nav>
  );
}

function App() {
  return (
    <Router>
      <Navbar />
      <main className="container mt-8 pb-8">
        <Routes>
          <Route path="/" element={<ProjectDashboard />} />
          <Route path="/project/:id/ingest" element={<PipelineLiveView />} />
          <Route path="/project/:id/traces" element={<TraceEditor />} />
          <Route path="/project/:id/toc" element={<TOCReviewer />} />
          <Route path="/project/:id/output" element={<ProjectOutput />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </Router>
  );
}

export default App;
