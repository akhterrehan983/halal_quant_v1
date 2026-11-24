export default function LoadingState({ label = 'Loading…' }) {
  return <div className="empty" role="status" aria-live="polite">{label}</div>
}