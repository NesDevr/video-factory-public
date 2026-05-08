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

export interface SubscribeCTAProps {
  cta_text?: string;
  subtext?: string;
  accent_color?: string;
}

// ── Component ───────────────────────────────────────────────

export const SubscribeCTA: React.FC<SubscribeCTAProps> = ({
  cta_text = "SUBSCRIBE",
  subtext = "Don't miss the next video!",
  accent_color = "#FF4444",
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Entrance: slide up + fade in
  const entranceSpring = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 160 },
  });
  const translateY = interpolate(entranceSpring, [0, 1], [60, 0]);
  const fadeIn = interpolate(entranceSpring, [0, 1], [0, 1]);

  // Exit: fade out in last 10 frames
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 10, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = fadeIn * fadeOut;

  // Button scale pop (staggered after entrance)
  const buttonSpring = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 200 },
    delay: 4,
  });
  const buttonScale = interpolate(buttonSpring, [0, 1], [0.6, 1]);

  // Bell wiggle — starts after button settles
  const bellDelay = 0.5 * fps;
  const bellWiggle =
    frame > bellDelay
      ? Math.sin(((frame - bellDelay) / fps) * 8) *
        interpolate(frame, [bellDelay, bellDelay + 15], [0, 4], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 0;

  // Pointing hand entrance (slides in from right, staggered)
  const handSpring = spring({
    frame,
    fps,
    config: { damping: 16, stiffness: 140 },
    delay: 10,
  });
  const handX = interpolate(handSpring, [0, 1], [40, 0]);
  const handOpacity = interpolate(handSpring, [0, 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Subtle hand bounce loop
  const bouncePhase = Math.max(0, frame - 30);
  const handBounceY = Math.sin((bouncePhase / fps) * 3) * 3;

  // Subtext fade in
  const subtextOpacity = interpolate(frame, [15, 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        opacity,
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 100,
      }}
    >
      {/* Semi-transparent backdrop scrim — only bottom portion */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: "100%",
          height: "40%",
          background:
            "linear-gradient(to top, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 60%, transparent 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Content container */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
          transform: `translateY(${translateY}px)`,
          zIndex: 1,
        }}
      >
        {/* Bell icon */}
        <div
          style={{
            fontSize: 40,
            transform: `rotate(${bellWiggle}deg)`,
          }}
        >
          🔔
        </div>

        {/* Button + hand row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          {/* Subscribe button */}
          <div
            style={{
              transform: `scale(${buttonScale})`,
              backgroundColor: accent_color,
              borderRadius: 14,
              padding: "16px 44px",
              boxShadow: "0 6px 24px rgba(0,0,0,0.4)",
            }}
          >
            <div
              style={{
                color: "#FFFFFF",
                fontSize: 34,
                fontWeight: 800,
                fontFamily: theme.font.sans,
                letterSpacing: 2,
                textTransform: "uppercase",
              }}
            >
              {cta_text}
            </div>
          </div>

          {/* Pointing hand */}
          <div
            style={{
              fontSize: 36,
              opacity: handOpacity,
              transform: `translateX(${handX}px) translateY(${handBounceY}px)`,
            }}
          >
            👈
          </div>
        </div>

        {/* Subtext */}
        <div
          style={{
            color: "rgba(255,255,255,0.85)",
            fontSize: 20,
            fontWeight: 600,
            fontFamily: theme.font.sans,
            letterSpacing: 1,
            opacity: subtextOpacity,
            textShadow: "0 2px 8px rgba(0,0,0,0.6)",
          }}
          >
          {subtext}
        </div>
      </div>
    </AbsoluteFill>
  );
};
