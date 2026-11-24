export default function StatusBadge({ children }) {
  const cls = String(children).toLowerCase().replaceAll(' ', '-').replaceAll('_', '-')
  return <span className={`pill ${cls}`}>{children}</span>
}