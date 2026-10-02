export default function LoadingSpinner({ label = 'Carregando...' }) {
  return (
    <div className="flex items-center gap-2 px-3 py-4 text-mute">
      <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      <span className="text-xs">{label}</span>
    </div>
  );
}
