import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { theme } from "../design/theme";

export interface ChannelWatermarkProps {
  text?: string;
  logo_path?: string;
  opacity?: number;
  position?: "bottom_right" | "bottom_left" | "top_right" | "top_left";
}

const POSITION_STYLES: Record<string, React.CSSProperties> = {
  bottom_right: { bottom: 30, right: 40 },
  bottom_left: { bottom: 30, left: 40 },
  top_right: { top: 30, right: 40 },
  top_left: { top: 30, left: 40 },
};

export const ChannelWatermark: React.FC<ChannelWatermarkProps> = ({
  text,
  logo_path,
  opacity = 0.4,
  position = "bottom_right",
}) => {
  if (!text && !logo_path) return null;

  const posStyle = POSITION_STYLES[position] || POSITION_STYLES.bottom_right;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          ...posStyle,
          display: "flex",
          alignItems: "center",
          gap: 12,
          opacity,
        }}
      >
        {logo_path && (
          <Img
            src={staticFile(logo_path)}
            style={{
              width: 48,
              height: 48,
              borderRadius: 8,
              objectFit: "contain",
            }}
          />
        )}
        {text && (
          <span
            style={{
              color: "#FFFFFF",
              fontSize: 30,
              fontWeight: 700,
              fontFamily: theme.font.sans,
              letterSpacing: 0.5,
              textShadow:
                "-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000, 0 0 8px rgba(0,0,0,0.6)",
            }}
          >
            {text}
          </span>
        )}
      </div>
    </AbsoluteFill>
  );
};
