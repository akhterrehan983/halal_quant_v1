export default function PageHeader({ eyebrow, title, chip }) {
  return (
    <div className="panel-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h3>{title}</h3>
      </div>
      {chip && <span className="paper-chip">{chip}</span>}
    </div>
  )
}