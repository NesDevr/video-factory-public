import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";

// ── Types ───────────────────────────────────────────────────

export interface TitleBannerProps {
  title: string;
  section_number?: number;
  icon_emoji?: string;
  accent_color?: string;
}

// ── Component ───────────────────────────────────────────────

export const TitleBanner: React.FC<TitleBannerProps> = ({
  title,
  icon_emoji,
  accent_color = theme.accent.blue,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Slide in from left
  const enterSpring = spring({
    frame,
    fps,
    config: { damping: 22, stiffness: 120 },
    durationInFrames: 25,
  });
  const slideX = interpolate(enterSpring, [0, 1], [-600, 0]);
  const enterOpacity = interpolate(enterSpring, [0, 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Fade out
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 20, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const opacity = enterOpacity * fadeOut;

  // Circle icon scale pop (staggered)
  const circleSpring = spring({
    frame: Math.max(0, frame - 10),
    fps,
    config: { damping: 14, stiffness: 200 },
    durationInFrames: 20,
  });
  const circleScale = interpolate(circleSpring, [0, 1], [0, 1]);

  const displayText = title;

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          top: 60,
          left: 0,
          opacity,
          transform: `translateX(${slideX}px)`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 20,
            backgroundColor: "rgba(0, 0, 0, 0.70)",
            backdropFilter: "blur(8px)",
            padding: "20px 40px 20px 24px",
            borderRadius: "0 16px 16px 0",
            boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
          }}
        >
          {/* Colored circle with icon */}
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: "50%",
              backgroundColor: accent_color,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              transform: `scale(${circleScale})`,
              boxShadow: `0 0 20px ${accent_color}50`,
            }}
            >
              <span
                style={{
                  fontSize: 24,
                  lineHeight: 1,
                }}
              >
                {icon_emoji || "●"}
              </span>
            </div>

          {/* Title text */}
          <div
            style={{
              color: "#FFFFFF",
              fontSize: 38,
              fontWeight: 700,
              fontFamily: theme.font.sans,
              lineHeight: 1.2,
              letterSpacing: 0.3,
              textShadow: "0 1px 4px rgba(0,0,0,0.3)",
              whiteSpace: "nowrap",
            }}
          >
            {displayText}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
