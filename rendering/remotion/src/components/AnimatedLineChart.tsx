import React, { useMemo } from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";
import type { DataPoint, HighlightRange } from "../lib/types";

export interface LineChartProps {
  data: { values: DataPoint[] };
  title: string;
  subtitle?: string;
  y_axis_label?: string;
  accent_color?: string;
  animation_duration_frames?: number;
  highlight_ranges?: HighlightRange[];
}

const PAD = { top: 240, right: 200, bottom: 140, left: 220 };

export const AnimatedLineChart: React.FC<LineChartProps> = ({
  data,
  title,
  subtitle,
  y_axis_label,
  accent_color = theme.accent.blue,
  animation_duration_frames = 90,
  highlight_ranges,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const values = data.values;
  if (values.length === 0) {
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

  // Chart area
  const chartW = width - PAD.left - PAD.right;
  const chartH = height - PAD.top - PAD.bottom;

  // Data bounds
  const numericValues = values.map((v) => v.value);
  const minVal = Math.min(...numericValues);
  const maxVal = Math.max(...numericValues);
  const valRange = maxVal - minVal || 1;
  const yPadding = valRange * 0.1;
  const yMin = minVal - yPadding;
  const yMax = maxVal + yPadding;

  // Map data to chart coordinates
  const points = useMemo(
    () =>
      values.map((d, i) => ({
        x: PAD.left + (i / (values.length - 1)) * chartW,
        y: PAD.top + chartH - ((d.value - yMin) / (yMax - yMin)) * chartH,
        date: d.date,
        value: d.value,
      })),
    [values, chartW, chartH, yMin, yMax],
  );

  // Build SVG path
  const pathD = useMemo(() => {
    return points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
      .join(" ");
  }, [points]);

  // Path length for dash animation
  const pathLength = useMemo(() => {
    let len = 0;
    for (let i = 1; i < points.length; i++) {
      const dx = points[i].x - points[i - 1].x;
      const dy = points[i].y - points[i - 1].y;
      len += Math.sqrt(dx * dx + dy * dy);
    }
    return len;
  }, [points]);

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

  const drawProgress = spring({
    frame: Math.max(0, frame - 15),
    fps,
    config: { damping: 200 },
    durationInFrames: animation_duration_frames,
  });

  // --- Grid ---

  const numGridLines = 6;
  const gridLines = useMemo(() => {
    const lines = [];
    for (let i = 0; i <= numGridLines; i++) {
      const ratio = i / numGridLines;
      const y = PAD.top + chartH * (1 - ratio);
      const val = yMin + (yMax - yMin) * ratio;
      lines.push({ y, label: val.toFixed(1) });
    }
    return lines;
  }, [chartH, yMin, yMax]);

  const xLabels = useMemo(() => {
    const count = Math.min(7, values.length);
    const step = Math.max(1, Math.floor((values.length - 1) / (count - 1)));
    const labels = [];
    for (let i = 0; i < values.length; i += step) {
      labels.push({ x: points[i].x, label: values[i].date });
    }
    return labels;
  }, [values, points]);

  // Highlight ranges
  const highlightRects = useMemo(() => {
    if (!highlight_ranges || highlight_ranges.length === 0) return [];
    return highlight_ranges.map((hr) => {
      const startIdx = values.findIndex((v) => v.date >= hr.start);
      const endIdx = values.findIndex((v) => v.date > hr.end);
      const si = startIdx >= 0 ? startIdx : 0;
      const ei = endIdx >= 0 ? endIdx : values.length - 1;
      return {
        x: points[si].x,
        width: points[ei].x - points[si].x,
        label: hr.label,
        color: hr.color,
      };
    });
  }, [highlight_ranges, values, points]);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      <svg width={width} height={height}>
        {/* Chart area fill — subtle panel */}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={chartW}
          height={chartH}
          fill={theme.surface}
          opacity={gridOpacity}
        />

        {/* Chart area border */}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={chartW}
          height={chartH}
          fill="none"
          stroke={theme.gridLine}
          strokeWidth={1.5}
          opacity={gridOpacity * 0.8}
        />

        {/* Highlight ranges */}
        {highlightRects.map((rect, i) => (
          <g key={`hl-${i}`} opacity={gridOpacity * 0.2}>
            <rect
              x={rect.x}
              y={PAD.top}
              width={rect.width}
              height={chartH}
              fill={rect.color}
            />
            <text
              x={rect.x + rect.width / 2}
              y={PAD.top + 24}
              textAnchor="middle"
              fill={rect.color}
              fontSize={16}
              fontFamily={theme.font.sans}
              opacity={0.8}
            >
              {rect.label}
            </text>
          </g>
        ))}

        {/* Horizontal grid lines */}
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
              x={PAD.left - 20}
              y={line.y + 7}
              textAnchor="end"
              fill={theme.text.secondary}
              fontSize={24}
              fontWeight={500}
              fontFamily={theme.font.mono}
            >
              {line.label}
            </text>
          </g>
        ))}

        {/* Y-axis unit at top */}
        {y_axis_label && (
          <text
            x={PAD.left - 20}
            y={PAD.top - 18}
            textAnchor="end"
            fill={theme.text.secondary}
            fontSize={24}
            fontWeight={500}
            fontFamily={theme.font.mono}
            opacity={gridOpacity}
          >
            {y_axis_label}
          </text>
        )}

        {/* X-axis labels */}
        {xLabels.map((label, i) => (
          <text
            key={`xlabel-${i}`}
            x={label.x}
            y={height - PAD.bottom + 44}
            textAnchor="middle"
            fill={theme.text.secondary}
            fontSize={24}
            fontWeight={600}
            fontFamily={theme.font.mono}
            opacity={gridOpacity}
          >
            {label.label}
          </text>
        ))}

        {/* Main line */}
        <path
          d={pathD}
          fill="none"
          stroke={accent_color}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={pathLength}
          strokeDashoffset={pathLength * (1 - drawProgress)}
        />

        {/* Data point dots — only for small datasets */}
        {points.length <= 20 &&
          points.map((p, i) => {
            const pointProgress = i / (points.length - 1);
            const visible = drawProgress >= pointProgress;
            if (!visible) return null;
            const dotScale = spring({
              frame: Math.max(
                0,
                frame - 15 - pointProgress * animation_duration_frames,
              ),
              fps,
              config: { damping: 15, stiffness: 200 },
              durationInFrames: 15,
            });
            return (
              <circle
                key={`dot-${i}`}
                cx={p.x}
                cy={p.y}
                r={4 * dotScale}
                fill={accent_color}
                stroke={theme.surface}
                strokeWidth={2}
              />
            );
          })}
      </svg>

      {/* Title — centered */}
      <div
        style={{
          position: "absolute",
          top: 40,
          left: 0,
          right: 0,
          textAlign: "center",
          transform: `translateY(${titleY}px)`,
          opacity: titleOpacity,
        }}
      >
        <div
          style={{
            color: accent_color,
            fontSize: 52,
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
              color: accent_color,
              fontSize: 26,
              fontWeight: 500,
              fontFamily: theme.font.sans,
              marginTop: 6,
              opacity: 0.8,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
