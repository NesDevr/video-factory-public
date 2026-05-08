import React, { useMemo } from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";
import type { BarItem } from "../lib/types";

export interface AnimatedBarChartProps {
  title: string;
  subtitle?: string;
  bars: BarItem[];
  accent_color?: string;
  value_suffix?: string;
}

export const AnimatedBarChart: React.FC<AnimatedBarChartProps> = ({
  title,
  subtitle,
  bars,
  accent_color = theme.accent.blue,
  value_suffix = "",
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  if (bars.length === 0) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: theme.bg,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <span
          style={{
            color: theme.text.muted,
            fontSize: 32,
            fontFamily: theme.font.sans,
          }}
        >
          No data available
        </span>
      </AbsoluteFill>
    );
  }

  // Generous padding — keep everything away from edges
  const PAD = {
    top: 220,
    right: 220,
    bottom: 140,
    left: 240,
  };

  const chartW = width - PAD.left - PAD.right;
  const chartH = height - PAD.top - PAD.bottom;
  const maxVal = Math.max(...bars.map((b) => b.value));

  // Bar layout — bars take 55% of each slot
  const slotWidth = chartW / bars.length;
  const barWidth = slotWidth * 0.55;
  const barOffset = (slotWidth - barWidth) / 2;

  // --- Animations ---

  const gridOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const titleY = interpolate(
    spring({ frame, fps, config: { damping: 200 }, durationInFrames: 30 }),
    [0, 1],
    [30, 0],
  );
  const titleOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // --- Grid lines ---

  const numGridLines = 4;
  const gridLines = useMemo(() => {
    const lines = [];
    for (let i = 0; i <= numGridLines; i++) {
      const ratio = i / numGridLines;
      const y = PAD.top + chartH * (1 - ratio);
      const val = maxVal * ratio;
      lines.push({
        y,
        label: val % 1 === 0 ? val.toString() : val.toFixed(1),
      });
    }
    return lines;
  }, [chartH, maxVal]);

  // Format value for display
  const formatValue = (v: number): string => {
    const str = v % 1 === 0 ? v.toString() : v.toFixed(1);
    return `${str}${value_suffix}`;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      <svg width={width} height={height}>
        <defs>
          <filter id="bar-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Grid lines */}
        {gridLines.map((line, i) => (
          <g key={`grid-${i}`} opacity={gridOpacity}>
            <line
              x1={PAD.left}
              y1={line.y}
              x2={width - PAD.right}
              y2={line.y}
              stroke={theme.gridLine}
              strokeWidth={1}
            />
            <text
              x={PAD.left - 16}
              y={line.y + 6}
              textAnchor="end"
              fill={theme.text.muted}
              fontSize={18}
              fontFamily={theme.font.mono}
            >
              {line.label}
            </text>
          </g>
        ))}

        {/* Bars */}
        {bars.map((bar, i) => {
          const barGrow = spring({
            frame: Math.max(0, frame - 15 - i * 6),
            fps,
            config: { damping: 15, stiffness: 80 },
            durationInFrames: 40,
          });

          const barH = (bar.value / maxVal) * chartH * barGrow;
          const x = PAD.left + i * slotWidth + barOffset;
          const y = PAD.top + chartH - barH;

          const opacity = interpolate(i, [0, bars.length - 1], [1, 0.75], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          return (
            <g key={`bar-${i}`}>
              {/* Glow */}
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barH}
                fill={accent_color}
                opacity={opacity * 0.3}
                rx={6}
                filter="url(#bar-glow)"
              />
              {/* Bar */}
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barH}
                fill={accent_color}
                opacity={opacity}
                rx={6}
              />
              {/* Value above bar */}
              <text
                x={x + barWidth / 2}
                y={y - 16}
                textAnchor="middle"
                fill={theme.text.primary}
                fontSize={28}
                fontWeight={700}
                fontFamily={theme.font.mono}
                opacity={barGrow}
              >
                {formatValue(bar.value)}
              </text>
              {/* Label below axis */}
              <text
                x={x + barWidth / 2}
                y={PAD.top + chartH + 45}
                textAnchor="middle"
                fill={theme.text.primary}
                fontSize={28}
                fontWeight={600}
                fontFamily={theme.font.sans}
                opacity={gridOpacity}
              >
                {bar.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: 50,
          left: PAD.left,
          transform: `translateY(${titleY}px)`,
          opacity: titleOpacity,
        }}
      >
        <div
          style={{
            color: theme.text.primary,
            fontSize: 50,
            fontWeight: 700,
            fontFamily: theme.font.sans,
            lineHeight: 1.2,
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div
            style={{
              color: theme.text.secondary,
              fontSize: 26,
              fontFamily: theme.font.sans,
              marginTop: 8,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
