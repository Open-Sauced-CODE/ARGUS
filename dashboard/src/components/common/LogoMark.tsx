import React from 'react';

interface LogoMarkProps {
  className?: string;
  size?: number;
  strokeWidth?: number;
}

export const LogoMark: React.FC<LogoMarkProps> = ({
  className = 'text-contour',
  size = 32,
  strokeWidth = 1.2,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Argus eye mark"
    >
      {/* Outer almond contour line */}
      <path
        d="M4 24C10 13 20 8 24 8C28 8 38 13 44 24C38 35 28 40 24 40C20 40 10 35 4 24Z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Mid almond contour line */}
      <path
        d="M9 24C13.5 16 19 13 24 13C29 13 34.5 16 39 24C34.5 32 29 35 24 35C19 35 13.5 32 9 24Z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeOpacity="0.85"
      />
      {/* Inner almond contour line */}
      <path
        d="M14 24C17 19 20.5 17 24 17C27.5 17 31 19 34 24C31 29 27.5 31 24 31C20.5 31 17 29 14 24Z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeOpacity="0.7"
      />
      {/* Central focal node (iris/pupil) */}
      <circle
        cx="24"
        cy="24"
        r="3"
        fill="currentColor"
        fillOpacity="0.9"
      />
    </svg>
  );
};

export const Logo: React.FC<{ className?: string }> = ({ className = '' }) => {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <LogoMark size={28} className="text-peacock" />
      <span className="font-headline text-2xl font-medium tracking-tight text-ink">
        Argus
      </span>
    </div>
  );
};
