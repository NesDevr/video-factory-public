import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";

export interface DonutGaugeProps {
  value: number; // 0-100
  unit?: string;
  accent_color?: string;
}

export const DonutGauge: React.FC<DonutGaugeProps> = ({
  value,
  unit = "%",
  accent_color = theme.accent.blue,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const clamped = Math.min(100, Math.max(0, value));

  // --- Animations ---

  const fadeIn = interpolate(frame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const arcProgress = spring({
    frame: Math.max(0, frame - 10),
    fps,
    config: { damping: 20, stiffness: 60 },
    durationInFrames: 60,
  });

  const countProgress = spring({
    frame: Math.max(0, frame - 10),
    fps,
    config: { damping: 20, stiffness: 60 },
    durationInFrames: 60,
  });

  const currentValue = clamped * countProgress;
  const displayValue =
    clamped % 1 === 0 ? Math.round(currentValue) : currentValue.toFixed(1);

  // --- SVG arc (derived from video dimensions) ---

  const cx = width / 2;
  const cy = height * 0.44;
  const radius = Math.min(width, height) * 0.23;
  const strokeWidth = radius * 0.16;
  const circumference = 2 * Math.PI * radius;
  const arcLength = (clamped / 100) * circumference * arcProgress;

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      <svg width={width} height={height}>
        <defs>
          <filter
            id="donut-glow"
            x="-20%"
            y="-20%"
            width="140%"
            height="140%"
          >
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Track ring */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={theme.gridLine}
          strokeWidth={strokeWidth}
          opacity={fadeIn}
        />

        {/* Active arc glow */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={accent_color}
          strokeWidth={strokeWidth + 8}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(-90, ${cx}, ${cy})`}
          opacity={0.3}
          filter="url(#donut-glow)"
        />

        {/* Active arc */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={accent_color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(-90, ${cx}, ${cy})`}
        />
      </svg>

      {/* Center content — number + label inside the ring */}
      <div
        style={{
          position: "absolute",
          top: cy,
          left: cx,
          transform: "translate(-50%, -50%)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          opacity: fadeIn,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <span
            style={{
              color: theme.text.primary,
              fontSize: 120,
              fontWeight: 700,
              fontFamily: theme.font.mono,
              lineHeight: 1,
            }}
          >
            {displayValue}
          </span>
          <span
            style={{
              color: accent_color,
              fontSize: 56,
              fontWeight: 700,
              fontFamily: theme.font.mono,
              marginLeft: 4,
            }}
          >
            {unit}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
