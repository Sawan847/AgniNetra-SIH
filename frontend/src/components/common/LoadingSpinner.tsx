export function LoadingSpinner({ size = 32 }: { size?: number }) {
  return (
    <div className="loading-spinner-container">
      <svg
        className="loading-spinner"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <circle
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray="31.4 31.4"
          strokeDashoffset="10"
        />
      </svg>
    </div>
  );
}
