import React, { useState, useEffect } from 'react';
import { request } from '../services/api';

// ── 반원 게이지 ──────────────────────────────────────────
const ARC_R = 80;
const ARC_LEN = Math.PI * ARC_R; // ~251.33

interface GaugeProps { score: number; safe: boolean; }

const RiskGauge: React.FC<GaugeProps> = ({ score, safe }) => {
  const [filled, setFilled] = useState(0);
  const percent = Math.round(score * 100);
  const color = safe ? '#22c55e' : '#ef4444';

  useEffect(() => {
    setFilled(0);
    const t = setTimeout(() => setFilled((percent / 100) * ARC_LEN), 60);
    return () => clearTimeout(t);
  }, [percent]);

  // 반원: 왼쪽(20,105) → 오른쪽(180,105), sweep=1 = 위쪽 아치(시계방향)
  const d = `M 20 105 A ${ARC_R} ${ARC_R} 0 0 1 180 105`;

  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 200 128" width="240" height="152">
        {/* 배경 트랙 */}
        <path d={d} fill="none" stroke="#f0f0f0" strokeWidth="15" strokeLinecap="round" />
        {/* 채워지는 아크 */}
        <path
          d={d}
          fill="none"
          stroke={color}
          strokeWidth="15"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${ARC_LEN}`}
          style={{ transition: 'stroke-dasharray 0.85s cubic-bezier(0.4, 0, 0.2, 1)' }}
        />
        {/* 0 / 100 끝 레이블 */}
        <text x="14" y="126" textAnchor="middle" fontSize="10" fill="#ccc">0</text>
        <text x="186" y="126" textAnchor="middle" fontSize="10" fill="#ccc">100</text>
        {/* 퍼센트 숫자 */}
        <text
          x="100" y="84"
          textAnchor="middle"
          fontSize="40"
          fontWeight="800"
          fill={color}
          style={{ fontFamily: 'inherit' }}
        >
          {percent}%
        </text>
        {/* 레이블 */}
        <text
          x="100" y="101"
          textAnchor="middle"
          fontSize="11"
          fill="#bbb"
          letterSpacing="1"
          style={{ fontFamily: 'inherit' }}
        >
          위험도
        </text>
      </svg>
    </div>
  );
};

// ─────────────────────────────────────────────────────────
const Landing: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [includeXai, setIncludeXai] = useState(false);
  const [includeSanitized, setIncludeSanitized] = useState(false);
  const [model, setModel] = useState<'small' | 'large'>('small');

  const handleTest = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await request('/v1/analyze/demo', {
        method: 'POST',
        body: JSON.stringify({
          prompt,
          model,
          include_xai: includeXai,
          include_sanitized: includeSanitized,
        }),
      });
      setResult(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getHighlightStyle = (weight: number): React.CSSProperties => {
    if (weight < 0.5) return {};
    const opacity = Math.min((weight - 0.5) * 2.2, 0.85);
    return {
      backgroundColor: `rgba(220, 38, 38, ${opacity})`,
      color: opacity > 0.45 ? '#fff' : 'inherit',
      borderRadius: '3px',
      padding: '1px 3px',
    };
  };

  return (
    <div>
      {/* Hero */}
      <section className="hero-section">
        <h1 className="hero-title">악성 프롬프트 탐지 시스템</h1>
        <p className="hero-sub">
          AI 모델이 입력된 프롬프트를 실시간으로 분석하여 악성 여부를 판단하고,<br />
          위험 토큰을 강조하거나 안전한 문장으로 순화합니다.
        </p>
      </section>

      {/* Demo Card */}
      <div className="demo-card">
        <div className="demo-card-header">
          <span className="demo-label">라이브 데모</span>
          <div className="toggle-group">
            <label className="toggle-label">
              <span>XAI 위험 강조</span>
              <button
                type="button"
                className={`toggle-btn ${includeXai ? 'on' : ''}`}
                onClick={() => setIncludeXai(v => !v)}
                aria-pressed={includeXai}
              >
                <span className="toggle-knob" />
              </button>
            </label>
            <label className="toggle-label">
              <span>LLM 순화 문장</span>
              <button
                type="button"
                className={`toggle-btn ${includeSanitized ? 'on' : ''}`}
                onClick={() => setIncludeSanitized(v => !v)}
                aria-pressed={includeSanitized}
              >
                <span className="toggle-knob" />
              </button>
            </label>
          </div>
        </div>

        <textarea
          className="prompt-textarea"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="분석할 프롬프트를 입력하세요..."
          rows={4}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleTest(); }
          }}
        />
        <div className="demo-card-footer">
          <span className="hint-text">Shift + Enter로 줄바꿈</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <select
              className="model-select"
              value={model}
              onChange={e => setModel(e.target.value as 'small' | 'large')}
              disabled={loading}
            >
              <option value="small">Small 모델</option>
              <option value="large">Large 모델</option>
            </select>
            <button className="analyze-btn" onClick={handleTest} disabled={loading || !prompt.trim()}>
              {loading && <span className="spinner" />}
              {loading ? '분석 중...' : '프롬프트 분석'}
            </button>
          </div>
        </div>
      </div>

      {error && <div className="error-box fade-in">{error}</div>}

      {result && (
        <div className="result-card fade-in">
          <h3 className="result-title">분석 결과</h3>

          {/* 게이지 + 메타 */}
          <div className="gauge-section">
            <RiskGauge score={result.score} safe={result.safe} />
            <div className="gauge-meta-row">
              <span className={`status-badge ${result.safe ? 'status-safe' : 'status-danger'}`}>
                {result.safe ? '✓ 안전' : '✕ 악성'}
              </span>
              <span className="gauge-time">처리 시간 {result.processingTime}ms</span>
            </div>
          </div>

          {/* XAI */}
          {'xai_highlights' in result && (
            <div className="result-section">
              <div className="section-label">
                <span className="section-icon">🔍</span>
                XAI 위험 토큰 분석
              </div>
              {result.xai_highlights && result.xai_highlights.length > 0 ? (
                <div className="xai-box">
                  {result.xai_highlights.map((h: any, idx: number) => (
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
                </div>
              ) : (
                <div className="info-note">위험 토큰이 감지되지 않았습니다.</div>
              )}
            </div>
          )}

          {/* 순화 */}
          {'sanitized_prompt' in result && (
            <div className="result-section">
              <div className="section-label">
                <span className="section-icon">✨</span>
                순화된 프롬프트
              </div>
              {result.sanitized_prompt ? (
                <div className="sanitized-box">{result.sanitized_prompt}</div>
              ) : (
                <div className="info-note">
                  {result.safe
                    ? '안전한 프롬프트로 분류되어 순화가 필요하지 않습니다.'
                    : '순화 처리 중 오류가 발생했습니다.'}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Landing;
