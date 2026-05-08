export default function Logo({ size = 48, style, ...rest }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role="img"
      aria-label="Face Attendance"
      style={{ color: 'var(--c-accent)', flexShrink: 0, ...style }}
      {...rest}
    >
      <defs>
        <radialGradient id="logo-glow" cx="50%" cy="45%" r="50%">
          <stop offset="0%"   stopColor="currentColor" stopOpacity="0.45" />
          <stop offset="55%"  stopColor="currentColor" stopOpacity="0.10" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
        <filter id="logo-soft" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="0.6" />
        </filter>
      </defs>

      <rect x="0" y="0" width="64" height="64" fill="url(#logo-glow)" />

      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M 8 14 L 8 8 L 14 8" />
        <path d="M 50 8 L 56 8 L 56 14" />
        <path d="M 56 50 L 56 56 L 50 56" />
        <path d="M 14 56 L 8 56 L 8 50" />
      </g>

      <g filter="url(#logo-soft)" opacity="0.75">
        <circle cx="32" cy="26" r="7" fill="none" stroke="currentColor" strokeWidth="2.6" />
        <path
          d="M 19 50 C 19 41, 25 36, 32 36 C 39 36, 45 41, 45 50"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      </g>

      <circle cx="32" cy="26" r="7" fill="none" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="M 19 50 C 19 41, 25 36, 32 36 C 39 36, 45 41, 45 50"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />

      <line
        x1="18" y1="32" x2="46" y2="32"
        stroke="currentColor"
        strokeWidth="0.75"
        strokeOpacity="0.55"
        strokeDasharray="1.2 1.8"
      />
    </svg>
  )
}
