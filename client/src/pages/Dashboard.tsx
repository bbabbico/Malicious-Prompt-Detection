import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts';
import { request } from '../services/api';

// removed mock stats

const RATIO_COLORS = ['#22c55e', '#ef4444'];

const BAR_COLOR = '#6366f1';
const BAR_HOVER_COLOR = '#4f46e5';

const TOOLTIP_STYLE: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: '8px 12px',
  fontSize: 13,
  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
};

const CustomTooltipBar = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip-popup" style={TOOLTIP_STYLE}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      <div style={{ color: '#6366f1' }}>{payload[0].value.toLocaleString()}건</div>
    </div>
  );
};

const CustomTooltipPie = ({ active, payload, total }: any) => {
  if (!active || !payload?.length) return null;
  const { name, value } = payload[0];
  const n = Number(value);
  const color = name === '악성' ? '#ef4444' : '#22c55e';
  const percent = total > 0 ? Math.round((n / total) * 100) : 0;
  return (
    <div className="tooltip-popup" style={TOOLTIP_STYLE}>
      <div style={{ fontWeight: 700, marginBottom: 2, color }}>{name}</div>
      <div style={{ color: '#555' }}>
        {n.toLocaleString()}건 ({percent}%)
      </div>
    </div>
  );
};

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<any>({
    today_requests: 0,
    month_requests: 0,
    avg_response_time_ms: 0,
    weekly_counts: [],
    ratio: []
  });

  useEffect(() => {
    request('/users/stats')
      .then(data => { if (data) setStats(data); })
      .catch(() => {});
  }, []);

  const ratioTotal = (stats.ratio || []).reduce((s: number, d: any) => s + d.value, 0);

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">대시보드</h2>
        <p className="page-desc">API 사용 현황을 한눈에 확인하세요.</p>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-number">{(stats.today_requests ?? 0).toLocaleString()}</div>
          <div className="stat-label">오늘의 API 호출 수</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📅</div>
          <div className="stat-number">{(stats.month_requests ?? 0).toLocaleString()}</div>
          <div className="stat-label">이번 달 호출 수</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">⚡</div>
          <div className="stat-number">
            {stats.avg_response_time_ms ?? 0}
            <span style={{ fontSize: 16, fontWeight: 500, color: '#888' }}>ms</span>
          </div>
          <div className="stat-label">평균 응답 속도</div>
        </div>
      </div>

      <div className="chart-grid">
        {/* 7일 호출 추이 */}
        <div className="card chart-card">
          <div className="chart-title">최근 7일 API 호출 추이</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={stats.weekly_counts || []} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <XAxis
                dataKey="day"
                tick={{ fontSize: 12, fill: '#999' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#ccc' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                content={<CustomTooltipBar />}
                cursor={{ fill: '#f5f3ff' }}
                animationDuration={0}
              />
              <Bar
                dataKey="count"
                name="호출 수"
                fill={BAR_COLOR}
                radius={[5, 5, 0, 0]}
                maxBarSize={40}
                activeBar={{ fill: BAR_HOVER_COLOR }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* 안전 vs 악성 도넛 */}
        <div className="card chart-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div className="chart-title" style={{ alignSelf: 'flex-start' }}>안전 vs 악성 비율</div>
          <PieChart width={260} height={220}>
            <Pie
              data={stats.ratio || []}
              cx={130}
              cy={95}
              innerRadius={52}
              outerRadius={78}
              dataKey="value"
              paddingAngle={3}
              startAngle={90}
              endAngle={-270}
              isAnimationActive={false}
            >
              {(stats.ratio || []).map((_: any, i: number) => (
                <Cell key={i} fill={RATIO_COLORS[i % RATIO_COLORS.length]} strokeWidth={0} />
              ))}
            </Pie>
            <Tooltip
              content={<CustomTooltipPie total={ratioTotal} />}
              animationDuration={0}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ paddingTop: '16px' }}
              formatter={(value: any) => (
                <span style={{ fontSize: 13, color: '#555' }}>{value}</span>
              )}
            />
          </PieChart>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
