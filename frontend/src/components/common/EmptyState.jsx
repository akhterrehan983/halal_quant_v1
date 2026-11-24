export default function EmptyState({ title = 'No data', hint = '' }) {
  return (
    <div className="empty-holdings">
      <b>{title}</b>
      {hint && <span>{hint}</span>}
    </div>
  )
}