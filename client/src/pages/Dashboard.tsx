import React, { useEffect, useState } from 'react';
import { request } from '../services/api';

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    request('/users/stats')
      .then(setStats)
      .catch(err => setError(err.message));
  }, []);

  return (
    <div>
      <h2>대시보드 요약</h2>
      {error && <div className="error">{error}</div>}
      {stats ? (
        <div className="flex gap-2">
          <div className="card">
            <h3>오늘의 API 호출 수</h3>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.today_requests || 0}</div>
          </div>
          <div className="card">
            <h3>이번 달 호출 수</h3>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.month_requests || 0}</div>
          </div>
          <div className="card">
            <h3>평균 응답 속도</h3>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.avg_response_time_ms || 0}ms</div>
          </div>
        </div>
      ) : (
        <div>통계를 불러오는 중...</div>
      )}
    </div>
  );
};

export default Dashboard;
