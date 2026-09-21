import React, { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useTrace } from '../contexts/TraceContext';
import { useAuth } from '../contexts/AuthContext';

export const Layout: React.FC = () => {
  const { traceId, resetTraceId } = useTrace();
  const { user, logout, login } = useAuth();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('adminpassword');
  const [authError, setAuthError] = useState<string | null>(null);
  const location = useLocation();

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      await login(username, password);
      setShowLoginModal(false);
    } catch {
      setAuthError('Authentication failed. Check credentials.');
    }
  };

  const navItems = [
    { to: '/', label: 'Submit Request', icon: '📝' },
    { to: '/requests/status', label: 'Request Status', icon: '⏳' },
    { to: '/history', label: 'Request History', icon: '📚' },
    { to: '/sources', label: 'Sources', icon: '🌐' },
    { to: '/information', label: 'Information Units', icon: '📄' },
    { to: '/conflicts', label: 'Conflicts', icon: '⚡' },
    { to: '/confidence', label: 'Confidence Matrix', icon: '📊' },
    { to: '/agents', label: 'Agents Solicited', icon: '🤖' },
    { to: '/traceability', label: 'Traceability', icon: '🔍' },
  ];

  return (
    <div className="inis-app">
      {/* Sidebar */}
      <aside className="inis-sidebar">
        <div className="sidebar-header">
          <div className="logo-badge">INIS</div>
          <div className="system-title">
            <h2>INIS Intelligence</h2>
            <span className="system-version">v0.1.0 • §31 Console</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <ul>
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    isActive || (item.to === '/' && location.pathname === '/')
                      ? 'active-nav-link'
                      : ''
                  }
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="sidebar-footer">
          <div className="trace-info-box">
            <span className="trace-label">Active Trace</span>
            <code className="trace-id" title={traceId}>
              {traceId.slice(0, 14)}…
            </code>
            <button
              className="btn-text"
              onClick={resetTraceId}
              title="Reset Trace ID"
              aria-label="New Trace"
            >
              🔄
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="inis-main-wrapper">
        {/* Topbar */}
        <header className="inis-topbar">
          <div className="topbar-breadcrumbs">
            <span className="breadcrumb-root">INIS Engine</span>
            <span className="breadcrumb-separator">/</span>
            <span className="breadcrumb-current">
              {navItems.find((n) => n.to === location.pathname)?.label || 'Console'}
            </span>
          </div>

          <div className="topbar-actions">
            <div className="status-indicator">
              <span className="status-dot online"></span>
              <span className="status-text">API Online</span>
            </div>

            {user ? (
              <div className="user-profile">
                <span className="user-badge" title={user.actor_id}>
                  👤 {user.actor_id.slice(0, 12)}…
                </span>
                <button className="btn-secondary btn-sm" onClick={logout}>
                  Logout
                </button>
              </div>
            ) : (
              <button
                className="btn-primary btn-sm"
                onClick={() => setShowLoginModal(true)}
              >
                Sign In
              </button>
            )}
          </div>
        </header>

        {/* Page Content */}
        <main className="inis-content-area">
          <Outlet />
        </main>
      </div>

      {/* Login Modal */}
      {showLoginModal && (
        <div className="modal-overlay" onClick={() => setShowLoginModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Authenticate to INIS</h3>
              <button
                className="btn-close"
                onClick={() => setShowLoginModal(false)}
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleLoginSubmit} className="modal-form">
              {authError && <div className="error-banner">{authError}</div>}
              <div className="form-group">
                <label htmlFor="username">Actor ID / Username</label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="password">Secret Key / Password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowLoginModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Authenticate
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Layout;
