import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const Layout: React.FC = () => {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <div className="container">
      <header style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '24px' }}>
        <div className="flex gap-2" style={{ alignItems: 'center' }}>
          <NavLink to="/" style={{ textDecoration: 'none' }}>
            <div style={{ fontWeight: 800, fontSize: '16px', letterSpacing: '-0.02em', color: '#111' }}>
              악성 프롬프트 탐지 시스템
            </div>
          </NavLink>

          <nav className="flex gap-2" style={{ marginLeft: 'auto', alignItems: 'center' }}>
            <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              프롬프트
            </NavLink>
            {isAuthenticated ? (
              <>
                <NavLink to="/dashboard" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                  대시보드
                </NavLink>
                <NavLink to="/keys" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                  API 키
                </NavLink>
                <NavLink to="/logs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                  탐지 로그
                </NavLink>
                <NavLink to="/docs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                  API 문서
                </NavLink>
                <button onClick={handleLogout} style={{ padding: '5px 12px', fontSize: 13 }}>
                  로그아웃
                </button>
              </>
            ) : (
              <>
                <NavLink to="/docs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                  API 문서
                </NavLink>
                <NavLink to="/login" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                  <button style={{ padding: '5px 12px', fontSize: 13 }}>로그인</button>
                </NavLink>
              </>
            )}
          </nav>
        </div>
      </header>

      <main>
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
