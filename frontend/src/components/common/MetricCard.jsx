export default function MetricCard({ label, value, sub, icon: Icon, tone = '' }) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <span className={`stat-icon ${tone}`}>{Icon && <Icon size={17} />}</span>
      </div>
      <div className="stat-value">{value ?? '—'}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  )
}