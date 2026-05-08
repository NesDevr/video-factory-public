import React from "react";
import { AbsoluteFill } from "remotion";
import { InfoSlide } from "./InfoSlide";
import type { TextOnlySlideProps } from "../lib/types";

export const TextOnlySlide: React.FC<TextOnlySlideProps> = ({
  text,
  title,
  variant,
  model,
  operation,
  prompt_text,
  background_color,
  background_tint_color,
  title_color,
  body_color,
  accent_color,
  highlighted_keywords,
  highlight_color,
}) => {
  if (variant === "ai_prompt_preview") {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: "#101418",
          color: "#E8EEF4",
          fontFamily:
            'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace',
          padding: 72,
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 26,
            height: "100%",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 32,
            }}
          >
            <div>
              <div
                style={{
                  fontSize: 44,
                  fontWeight: 800,
                  color: "#FFFFFF",
                  marginBottom: 14,
                }}
              >
                {title || "AI Image Prompt"}
              </div>
              <div style={{ fontSize: 25, color: "#9FB0C3" }}>
                AI image generation skipped for test preview
              </div>
            </div>
            <div
              style={{
                textAlign: "right",
                fontSize: 24,
                lineHeight: 1.45,
                color: "#C9D6E2",
                maxWidth: 720,
              }}
            >
              <div>Model: {model || "unknown"}</div>
              <div>Operation: {operation || "unknown"}</div>
            </div>
          </div>

          <PromptBlock label="Prompt" text={prompt_text || text} />
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <InfoSlide
      text={text}
      title={title}
      background_color={background_color}
      background_tint_color={background_tint_color}
      title_color={title_color}
      body_color={body_color}
      accent_color={accent_color}
      highlighted_keywords={highlighted_keywords}
      highlight_color={highlight_color}
    />
  );
};

const PromptBlock: React.FC<{ label: string; text: string }> = ({ label, text }) => (
  <div
    style={{
      flex: 1,
      minHeight: 0,
      display: "flex",
      flexDirection: "column",
      gap: 12,
    }}
  >
    <div
      style={{
        fontSize: 24,
        fontWeight: 800,
        color: "#76D1FF",
        textTransform: "uppercase",
        letterSpacing: 0,
      }}
    >
      {label}
    </div>
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        backgroundColor: "#17212B",
        border: "1px solid #2A3A4A",
        borderRadius: 8,
        padding: 22,
        fontSize: 23,
        lineHeight: 1.42,
        color: "#E8EEF4",
      }}
    >
      {text}
    </div>
  </div>
);
