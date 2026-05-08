import React, { useMemo } from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";

export interface FactHighlightProps {
  value: string;
  label: string;
  unit?: string;
  accent_color?: string;
}

export const FactHighlight: React.FC<FactHighlightProps> = ({
  value,
  label,
  unit,
  accent_color = theme.accent.blue,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Parse numeric value for count-up animation
  const parsed = useMemo(() => {
    const stripped = value.replace(/[^0-9.\-]/g, "");
    const num = parseFloat(stripped);
    if (isNaN(num)) return null;
    const idx = value.indexOf(stripped);
    return {
      num,
      prefix: value.slice(0, idx),
      suffix: value.slice(idx + stripped.length),
      decimals: stripped.includes(".") ? stripped.split(".")[1].length : 0,
    };
  }, [value]);

  // Fade in/out
  const fadeIn = interpolate(frame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 15, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = fadeIn * fadeOut;

  // Count-up spring (starts frame 5)
  const countProgress = spring({
    frame: Math.max(0, frame - 5),
    fps,
    config: { damping: 25, stiffness: 80 },
    durationInFrames: 45,
  });

  const displayValue = useMemo(() => {
    if (!parsed) return value;
    const current = parsed.num * countProgress;
    const formatted = current.toFixed(parsed.decimals);
    return `${parsed.prefix}${formatted}${parsed.suffix}`;
  }, [parsed, value, countProgress]);

  // Value scale pop
  const valueScale = interpolate(
    spring({
      frame: Math.max(0, frame - 5),
      fps,
      config: { damping: 12, stiffness: 150 },
      durationInFrames: 30,
    }),
    [0, 1],
    [0.7, 1],
  );
  const valueOpacity = interpolate(frame, [3, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Unit fade in (starts frame 15)
  const unitOpacity = interpolate(frame, [15, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Label slides up (starts frame 20)
  const labelSpring = spring({
    frame: Math.max(0, frame - 20),
    fps,
    config: { damping: 20, stiffness: 100 },
    durationInFrames: 25,
  });
  const labelY = interpolate(labelSpring, [0, 1], [30, 0]);
  const labelOpacity = interpolate(labelSpring, [0, 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Accent underline (starts frame 30)
  const lineProgress = spring({
    frame: Math.max(0, frame - 30),
    fps,
    config: { damping: 200 },
    durationInFrames: 30,
  });

  return (
    <AbsoluteFill style={{ opacity }}>
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <div
          style={{
            position: "absolute",
            width: "100%",
            height: "100%",
            background: `radial-gradient(ellipse 45% 50% at 50% 50%, ${theme.scrim.center} 0%, ${theme.scrim.mid} 40%, ${theme.scrim.edge} 100%)`,
            pointerEvents: "none",
          }}
        />
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 12,
            transform: `scale(${valueScale})`,
            opacity: valueOpacity,
          }}
        >
          <span
            style={{
              color: accent_color,
              fontSize: 120,
              fontWeight: 800,
              fontFamily: theme.font.mono,
              lineHeight: 1,
              letterSpacing: -2,
              textShadow: `0 0 25px ${accent_color}40, 0 2px 12px rgba(0,0,0,0.6)`,
            }}
          >
            {displayValue}
          </span>
          {unit && (
            <span
              style={{
                color: "rgba(255,255,255,0.8)",
                fontSize: 40,
                fontWeight: 500,
                fontFamily: theme.font.sans,
                opacity: unitOpacity,
                textShadow: "0 1px 6px rgba(0,0,0,0.6)",
              }}
            >
              {unit}
            </span>
          )}
        </div>

        <div
          style={{
            width: 120,
            height: 3,
            backgroundColor: accent_color,
            marginTop: 28,
            borderRadius: 2,
            transform: `scaleX(${lineProgress})`,
            transformOrigin: "center center",
            opacity: 0.8,
            boxShadow: `0 0 15px ${accent_color}40`,
          }}
        />

        <div
          style={{
            marginTop: 24,
            transform: `translateY(${labelY}px)`,
            opacity: labelOpacity,
            textAlign: "center",
            maxWidth: "70%",
          }}
        >
          <span
            style={{
              color: "#FFFFFF",
              fontSize: 36,
              fontWeight: 500,
              fontFamily: theme.font.sans,
              lineHeight: 1.3,
              textShadow: "0 1px 10px rgba(0,0,0,0.7)",
            }}
          >
            {label}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
