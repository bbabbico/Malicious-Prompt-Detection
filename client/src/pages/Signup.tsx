import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { request } from '../services/api';

const Signup: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await request('/users/signup', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      navigate('/login');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card auth-card">
      <div className="auth-title">회원가입</div>
      <div className="auth-sub">계정을 만들고 API 키를 발급받으세요.</div>

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
          {loading ? '가입 중...' : '회원가입'}
        </button>
      </form>

      <div className="auth-footer">
        이미 계정이 있으신가요? <Link to="/login">로그인</Link>
      </div>
    </div>
  );
};

export default Signup;
