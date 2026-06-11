import React, { useEffect, useState } from 'react';
import { request } from '../services/api';

// removed mock logs

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);

  useEffect(() => {
    request('/users/logs')
      .then(data => { setLogs(data || []); })
      .catch(() => { setLogs([]); });
  }, []);

  const getHighlightStyle = (weight: number): React.CSSProperties => {
    if (weight < 0.5) return {};
    const opacity = Math.min((weight - 0.5) * 2.2, 0.85);
    return {
      backgroundColor: `rgba(220, 38, 38, ${opacity})`,
      color: opacity > 0.45 ? '#fff' : 'inherit',
      borderRadius: '3px',
      padding: '0 2px',
    };
  };

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">탐지 로그</h2>
        <p className="page-desc">API를 통해 분석된 프롬프트의 탐지 내역을 확인하세요.</p>
      </div>

      {logs.length === 0 ? (
        <div className="empty-state">기록된 탐지 로그가 없습니다.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>일시</th>
              <th>프롬프트</th>
              <th>결과</th>
              <th>위험도</th>
              <th>처리 시간</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log, i) => {
              const isMalicious = log.risk_score > 50;
              return (
                <tr key={i}>
                  <td style={{ whiteSpace: 'nowrap', fontSize: 13, color: '#777' }}>
                    {new Date(log.created_at).toLocaleString('ko-KR')}
                  </td>
                  <td style={{ maxWidth: 380, fontSize: 13 }}>
                    {log.xai_highlights && log.xai_highlights.length > 0 ? (
                      <span>
                        {log.xai_highlights.map((h: any, idx: number) => (
                          <span 
                            key={idx} 
                            style={getHighlightStyle(h.weight)}
                            title={`기여도: ${Math.round(h.weight * 100)}%`}
                          >
                            {h.text}
                            {h.weight >= 0.5 && (
                              <span style={{ fontSize: '0.75em', marginLeft: '2px', opacity: 0.9, fontWeight: 500 }}>
                                {Math.round(h.weight * 100)}%
                              </span>
                            )}
                          </span>
                        ))}
                      </span>
                    ) : (
                      <span style={{ overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                        {log.prompt}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`tbl-badge ${isMalicious ? 'tbl-danger' : 'tbl-safe'}`}>
                      {isMalicious ? '악성' : '안전'}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div className="score-mini-track">
                        <div
                          className="score-mini-fill"
                          style={{
                            width: `${log.risk_score}%`,
                            background: isMalicious ? '#ef4444' : '#22c55e'
                          }}
                        />
                      </div>
                      <span style={{ fontSize: 13, fontWeight: 600, color: isMalicious ? '#b91c1c' : '#15803d' }}>
                        {log.risk_score}%
                      </span>
                    </div>
                  </td>
                  <td style={{ fontSize: 13, color: '#777', whiteSpace: 'nowrap' }}>
                    {log.process_time_ms}ms
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default Logs;
