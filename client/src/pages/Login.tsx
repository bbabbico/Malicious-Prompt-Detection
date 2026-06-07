import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { request } from '../services/api';

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await request('/users/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      login(data.access_token);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card auth-card">
      <div className="auth-title">로그인</div>
      <div className="auth-sub">계정에 로그인하여 API를 관리하세요.</div>

      {error && <div className="error-box" style={{ marginBottom: 16 }}>{error}</div>}

      <form onSubmit={handleSubmit} className="flex-col gap-2">
        <div className="form-group">
          <label className="form-label">이메일</label>
          <input
            className="form-input"
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
          />
        </div>
        <div className="form-group">
          <label className="form-label">비밀번호</label>
          <input
            className="form-input"
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="비밀번호를 입력하세요"
            required
          />
        </div>
        <button type="submit" className="btn-full" disabled={loading} style={{ marginTop: 4 }}>
          {loading && <span className="spinner" />}
          {loading ? '로그인 중...' : '로그인'}
        </button>
      </form>

      <div className="auth-footer">
        계정이 없으신가요? <Link to="/signup">회원가입</Link>
      </div>
    </div>
  );
};

export default Login;
