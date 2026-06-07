import React, { useEffect, useState } from 'react';
import { request } from '../services/api';

const ApiKeys: React.FC = () => {
  const [keys, setKeys] = useState<any[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const loadKeys = () => {
    request('/users/keys')
      .then(setKeys)
      .catch(err => setError(err.message));
  };

  useEffect(() => { loadKeys(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const data = await request('/users/keys', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim() })
      });
      setNewKey(data.key);
      setName('');
      setCopied(false);
      loadKeys();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleCopy = () => {
    if (!newKey) return;
    navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDelete = async (keyId: string) => {
    setDeleting(keyId);
    try {
      await request(`/users/keys/${keyId}`, { method: 'DELETE' });
      loadKeys();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">API 키 관리</h2>
        <p className="page-desc">B2B API 연동에 사용할 키를 발급하고 관리하세요.</p>
      </div>

      {error && <div className="error-box" style={{ marginBottom: 16 }}>{error}</div>}

      {newKey && (
        <div className="key-alert">
          <div className="key-alert-title">새 API 키가 발급되었습니다</div>
          <p style={{ fontSize: 13, color: '#166534', margin: '0 0 4px' }}>
            지금 즉시 복사해 두세요. 이 키는 다시 확인할 수 없습니다.
          </p>
          <div className="key-value">{newKey}</div>
          <div className="flex gap-1" style={{ marginTop: 8 }}>
            <button className="btn-sm" onClick={handleCopy}>
              {copied ? '✓ 복사됨' : '클립보드 복사'}
            </button>
            <button className="btn-sm btn-outline" onClick={() => setNewKey(null)}>닫기</button>
          </div>
        </div>
      )}

      <div className="key-create-card">
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: '#111' }}>새 키 생성</div>
        <form onSubmit={handleCreate} className="flex gap-1">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="키 이름 (예: 프로덕션 서버)"
            style={{ flex: 1, maxWidth: 'none' }}
            required
          />
          <button type="submit">생성</button>
        </form>
      </div>

      {keys.length === 0 ? (
        <div className="empty-state">발급된 API 키가 없습니다. 위에서 새 키를 생성해 보세요.</div>
      ) : (
        <div>
          {keys.map(k => (
            <div className="key-card" key={k.id}>
              <div className="key-card-info">
                <div className="key-card-name">{k.name}</div>
                <div className="key-card-mask">{k.maskedKey}</div>
                <div className="key-card-date">
                  생성: {new Date(k.createdAt).toLocaleDateString('ko-KR')}
                  {k.lastUsed && ` · 마지막 사용: ${new Date(k.lastUsed).toLocaleDateString('ko-KR')}`}
                </div>
              </div>
              <button
                className="btn-sm btn-danger"
                onClick={() => handleDelete(k.id)}
                disabled={deleting === k.id}
              >
                {deleting === k.id ? '삭제 중...' : '삭제'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ApiKeys;
