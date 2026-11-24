export default function ErrorState({ message, onRetry }) {
  return (
    <div className="error" role="alert">
      {message}
      {onRetry && (
        <button type="button" className="icon-btn" style={{ marginLeft: 8 }} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}