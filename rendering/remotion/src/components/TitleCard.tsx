import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";

export interface TitleCardProps {
  title: string;
  accent_color?: string;
}

export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  accent_color = theme.accent.blue,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Fade in (0 → 10 frames)
  const fadeIn = interpolate(frame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Fade out (last 15 frames)
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 15, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const opacity = fadeIn * fadeOut;

  // Accent underline draws left → right (starts frame 8)
  const lineProgress = spring({
    frame: Math.max(0, frame - 8),
    fps,
    config: { damping: 200 },
    durationInFrames: 35,
  });

  // Title spring entrance with vertical slide (starts frame 5)
  const titleSpring = spring({
    frame: Math.max(0, frame - 5),
    fps,
    config: { damping: 18, stiffness: 120 },
    durationInFrames: 30,
  });
  const titleY = interpolate(titleSpring, [0, 1], [40, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 0.4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const lineWidth = 200;

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
            background: `radial-gradient(ellipse 50% 45% at 50% 50%, ${theme.scrim.center} 0%, ${theme.scrim.mid} 40%, ${theme.scrim.edge} 100%)`,
            pointerEvents: "none",
          }}
        />
        <div
          style={{
            transform: `translateY(${titleY}px)`,
            opacity: titleOpacity,
            textAlign: "center",
            maxWidth: "80%",
          }}
        >
          <div
            style={{
              color: "#FFFFFF",
              fontSize: 72,
              fontWeight: 700,
              fontFamily: theme.font.sans,
              lineHeight: 1.15,
              letterSpacing: -1,
              textShadow: "0 2px 20px rgba(0,0,0,0.7), 0 0 40px rgba(0,0,0,0.3)",
            }}
          >
            {title}
          </div>
        </div>

        <div
          style={{
            width: lineWidth,
            height: 4,
            backgroundColor: accent_color,
            marginTop: 24,
            borderRadius: 2,
            transform: `scaleX(${lineProgress})`,
            transformOrigin: "left center",
            boxShadow: `0 0 20px ${accent_color}60`,
          }}
        />

      </div>
    </AbsoluteFill>
  );
};
