import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";
import type { ComparisonItem } from "../lib/types";

export interface ComparisonBarsProps {
  title: string;
  items: ComparisonItem[];
  accent_color?: string;
  value_suffix?: string;
}

const BAR_HEIGHT = 56;
const ITEM_HEIGHT = 110;
const ITEM_GAP = 28;

export const ComparisonBars: React.FC<ComparisonBarsProps> = ({
  title,
  items,
  accent_color = theme.accent.blue,
  value_suffix = "",
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // Derive layout from video dimensions
  const pad = width * 0.065;
  const labelWidth = width * 0.18;
  const barLeft = pad + labelWidth + pad * 0.4;
  const barRight = width - pad * 5;
  const barAreaWidth = barRight - barLeft;

  if (items.length === 0) {
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

  const maxVal = Math.max(...items.map((it) => it.value));

  // --- Animations ---

  const titleOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(
    spring({ frame, fps, config: { damping: 200 }, durationInFrames: 30 }),
    [0, 1],
    [30, 0],
  );

  // Center title + bars as one block
  const titleHeight = 130;
  const gapTitleBars = 60;
  const totalHeight =
    items.length * ITEM_HEIGHT + (items.length - 1) * ITEM_GAP;
  const blockHeight = titleHeight + gapTitleBars + totalHeight;
  const blockTop = (height - blockHeight) / 2;
  const startY = blockTop + titleHeight + gapTitleBars;

  // Format value for display
  const formatValue = (v: number): string => {
    const str = v % 1 === 0 ? v.toString() : v.toFixed(1);
    return `${str}${value_suffix}`;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: blockTop,
          left: pad,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
        }}
      >
        <div
          style={{
            color: theme.text.primary,
            fontSize: 52,
            fontWeight: 700,
            fontFamily: theme.font.sans,
            lineHeight: 1.2,
          }}
        >
          {title}
        </div>
      </div>

      {/* Items */}
      {items.map((item, i) => {
        const barGrow = spring({
          frame: Math.max(0, frame - 15 - i * 8),
          fps,
          config: { damping: 15, stiffness: 80 },
          durationInFrames: 40,
        });

        const labelFade = interpolate(frame, [5 + i * 5, 15 + i * 5], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const barW = (item.value / maxVal) * barAreaWidth * barGrow;
        const y = startY + i * (ITEM_HEIGHT + ITEM_GAP);

        const opacity = interpolate(i, [0, items.length - 1], [1, 0.75], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: y,
              left: 0,
              right: 0,
              height: ITEM_HEIGHT,
            }}
          >
            {/* Label */}
            <div
              style={{
                position: "absolute",
                left: pad,
                width: labelWidth,
                top: 0,
                height: ITEM_HEIGHT,
                display: "flex",
                alignItems: "center",
                color: theme.text.primary,
                fontSize: 32,
                fontFamily: theme.font.sans,
                fontWeight: 600,
                opacity: labelFade,
              }}
            >
              {item.label}
            </div>

            {/* Track */}
            <div
              style={{
                position: "absolute",
                left: barLeft,
                top: (ITEM_HEIGHT - BAR_HEIGHT) / 2,
                width: barAreaWidth,
                height: BAR_HEIGHT,
                backgroundColor: theme.gridLine,
                borderRadius: 10,
                opacity: labelFade * 0.5,
              }}
            />

            {/* Bar */}
            <div
              style={{
                position: "absolute",
                left: barLeft,
                top: (ITEM_HEIGHT - BAR_HEIGHT) / 2,
                width: barW,
                height: BAR_HEIGHT,
                backgroundColor: accent_color,
                borderRadius: 10,
                opacity,
                boxShadow: `0 0 20px ${accent_color}40`,
              }}
            />

            {/* Value */}
            <div
              style={{
                position: "absolute",
                left: barLeft + barW + 20,
                top: 0,
                height: ITEM_HEIGHT,
                display: "flex",
                alignItems: "center",
                color: theme.text.primary,
                fontSize: 30,
                fontWeight: 700,
                fontFamily: theme.font.mono,
                whiteSpace: "nowrap",
                opacity: barGrow,
              }}
            >
              {formatValue(item.value)}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
