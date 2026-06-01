import React, { useEffect, useState } from 'react';
import { request } from '../services/api';

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    request('/users/logs')
      .then(setLogs)
      .catch(err => setError(err.message));
  }, []);

  const getHighlightStyle = (weight: number) => {
    if (weight <= 0) return {};
    const opacity = Math.min(weight * 2, 0.8);
    return {
      backgroundColor: `rgba(220, 38, 38, ${opacity})`,
      color: opacity > 0.5 ? '#fff' : 'inherit',
      borderRadius: '2px',
      padding: '0 2px'
    };
  };

  return (
    <div>
      <h2>탐지 로그</h2>
      {error && <div className="error">{error}</div>}
      
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
          {logs.map((log, i) => (
            <tr key={i}>
              <td>{new Date(log.created_at).toLocaleString()}</td>
              <td style={{ maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'normal', lineHeight: '1.5' }}>
                {log.xai_highlights && log.xai_highlights.length > 0 ? (
                  log.xai_highlights.map((h: any, idx: number) => (
                    <span key={idx} style={getHighlightStyle(h.weight)}>
                      {h.text}
                    </span>
                  ))
                ) : (
                  log.prompt
                )}
              </td>
              <td>{log.risk_score > 50 ? <span className="error">악성</span> : <span className="success">안전</span>}</td>
              <td>{log.risk_score}%</td>
              <td>{log.process_time_ms}ms</td>
            </tr>
          ))}
          {logs.length === 0 && (
            <tr><td colSpan={5}>기록된 로그가 없습니다.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default Logs;
