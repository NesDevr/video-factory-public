import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";
import { renderHighlightedText } from "../lib/highlightWords";

// ── Types ───────────────────────────────────────────────────

export interface InfoSlideProps {
  text: string;
  title?: string;
  illustration_url?: string;
  layout?: "image-left" | "image-right";
  background_color?: string;
  background_tint_color?: string;
  title_color?: string;
  body_color?: string;
  accent_color?: string;
  highlighted_keywords?: string[];
  highlight_color?: string;
}

// ── Helpers ─────────────────────────────────────────────────

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function lighten(hex: string, amount: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const lr = Math.round(r + (255 - r) * amount);
  const lg = Math.round(g + (255 - g) * amount);
  const lb = Math.round(b + (255 - b) * amount);
  return `#${lr.toString(16).padStart(2, "0")}${lg.toString(16).padStart(2, "0")}${lb.toString(16).padStart(2, "0")}`;
}

function darken(hex: string, amount: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const dr = Math.round(r * (1 - amount));
  const dg = Math.round(g * (1 - amount));
  const db = Math.round(b * (1 - amount));
  return `#${dr.toString(16).padStart(2, "0")}${dg.toString(16).padStart(2, "0")}${db.toString(16).padStart(2, "0")}`;
}

/** Parse text into paragraphs and bullet items. */
function parseTextBlocks(
  text: string,
): { type: "paragraph" | "bullet"; content: string }[] {
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      const trimmed = line.trim();
      if (/^[•\-*]\s/.test(trimmed)) {
        return {
          type: "bullet" as const,
          content: trimmed.replace(/^[•\-*]\s*/, ""),
        };
      }
      return { type: "paragraph" as const, content: trimmed };
    });
}

/** Deterministic pseudo-random 0..1 from seed. */
function seededRand(seed: number): number {
  const x = Math.sin(seed * 9301 + 49297) * 49297;
  return x - Math.floor(x);
}

// ── Decorative sub-components ───────────────────────────────

interface FloatingShape {
  x: number;
  y: number;
  size: number;
  kind: "circle" | "ring" | "cross" | "dot";
  speed: number;
  angle: number;
  rotSpeed: number;
  alpha: number;
}

function generateShapes(count: number): FloatingShape[] {
  const kinds: FloatingShape["kind"][] = ["circle", "ring", "cross", "dot"];
  const shapes: FloatingShape[] = [];
  for (let i = 0; i < count; i++) {
    shapes.push({
      x: seededRand(i * 7 + 1) * 1920,
      y: seededRand(i * 7 + 2) * 1080,
      size: 8 + seededRand(i * 7 + 3) * 30,
      kind: kinds[Math.floor(seededRand(i * 7 + 4) * kinds.length)],
      speed: 0.15 + seededRand(i * 7 + 5) * 0.35,
      angle: seededRand(i * 7 + 6) * Math.PI * 2,
      rotSpeed: (seededRand(i * 7 + 7) - 0.5) * 0.8,
      alpha: 0.04 + seededRand(i * 7 + 8) * 0.07,
    });
  }
  return shapes;
}

const FLOATING_SHAPES = generateShapes(18);

const FloatingBackground: React.FC<{
  accent: string;
  frame: number;
  fps: number;
}> = ({ accent, frame, fps }) => {
  const t = frame / fps;

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {FLOATING_SHAPES.map((s, i) => {
        const dx = Math.cos(s.angle) * s.speed * t * 30;
        const dy = Math.sin(s.angle) * s.speed * t * 30;
        const rot = s.rotSpeed * t * 40;
        const x = ((s.x + dx) % 2100) - 90;
        const y = ((s.y + dy) % 1260) - 90;
        const color = hexToRgba(accent, s.alpha);

        const shared: React.CSSProperties = {
          position: "absolute",
          left: x,
          top: y,
          transform: `rotate(${rot}deg)`,
        };

        if (s.kind === "circle") {
          return (
            <div
              key={i}
              style={{
                ...shared,
                width: s.size,
                height: s.size,
                borderRadius: "50%",
                backgroundColor: color,
              }}
            />
          );
        }
        if (s.kind === "ring") {
          return (
            <div
              key={i}
              style={{
                ...shared,
                width: s.size,
                height: s.size,
                borderRadius: "50%",
                border: `2px solid ${color}`,
              }}
            />
          );
        }
        if (s.kind === "dot") {
          return (
            <div
              key={i}
              style={{
                ...shared,
                width: s.size * 0.35,
                height: s.size * 0.35,
                borderRadius: "50%",
                backgroundColor: color,
              }}
            />
          );
        }
        // cross
        const arm = s.size;
        const thick = Math.max(2, s.size * 0.2);
        return (
          <div key={i} style={shared}>
            <div
              style={{
                position: "absolute",
                width: arm,
                height: thick,
                backgroundColor: color,
                borderRadius: thick / 2,
                top: (arm - thick) / 2,
                left: 0,
              }}
            />
            <div
              style={{
                position: "absolute",
                width: thick,
                height: arm,
                backgroundColor: color,
                borderRadius: thick / 2,
                top: 0,
                left: (arm - thick) / 2,
              }}
            />
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const DotWave: React.FC<{
  accent: string;
  progress: number;
  width: number;
}> = ({ accent, progress, width }) => {
  const dotCount = 40;
  const dots: React.ReactNode[] = [];

  for (let i = 0; i < dotCount; i++) {
    const t = i / (dotCount - 1);
    const x = t * width;
    const y = 45 + Math.sin(t * Math.PI * 2.5 + 0.5) * 22;
    const size = 4 + seededRand(i + 7) * 3;
    const dotProgress = interpolate(
      progress,
      [t * 0.6, t * 0.6 + 0.4],
      [0, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );
    dots.push(
      <div
        key={i}
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: size,
          height: size,
          borderRadius: "50%",
          backgroundColor: hexToRgba(accent, 0.15 + seededRand(i + 3) * 0.2),
          transform: `scale(${dotProgress})`,
          opacity: dotProgress,
        }}
      />,
    );
  }
  return (
    <div
      style={{ position: "absolute", top: 0, left: 80, right: 80, height: 90 }}
    >
      {dots}
    </div>
  );
};

const AccentCross: React.FC<{
  x: number;
  y: number;
  size: number;
  color: string;
  opacity: number;
  rotation: number;
  scale: number;
}> = ({ x, y, size, color, opacity, rotation, scale }) => {
  const arm = size;
  const thickness = Math.max(2, size * 0.25);
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        opacity,
        transform: `rotate(${rotation}deg) scale(${scale})`,
      }}
    >
      <div
        style={{
          position: "absolute",
          width: arm,
          height: thickness,
          backgroundColor: color,
          borderRadius: thickness / 2,
          top: (arm - thickness) / 2,
          left: 0,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: thickness,
          height: arm,
          backgroundColor: color,
          borderRadius: thickness / 2,
          top: 0,
          left: (arm - thickness) / 2,
        }}
      />
    </div>
  );
};

const AccentDiamond: React.FC<{
  x: number;
  y: number;
  size: number;
  color: string;
  opacity: number;
  scale: number;
}> = ({ x, y, size, color, opacity, scale }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: size,
      height: size,
      backgroundColor: color,
      opacity,
      transform: `rotate(45deg) scale(${scale})`,
      borderRadius: 2,
    }}
  />
);

// ── Main component ──────────────────────────────────────────

export const InfoSlide: React.FC<InfoSlideProps> = ({
  text,
  title,
  illustration_url,
  layout = "image-right",
  background_color,
  background_tint_color,
  title_color,
  body_color,
  accent_color = "#2E86DE",
  highlighted_keywords = [],
  highlight_color,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const titleColor = title_color ?? "#0F1A30";
  const bodyColor = body_color ?? "#1E2D45";
  const bgBase = background_color ?? "#FFFFFF";
  const bgTint = background_tint_color ?? lighten(accent_color, 0.95);
  const resolvedHighlightColor = highlight_color ?? darken(accent_color, 0.15);

  // ── Global fade in / out ──
  const fadeIn = interpolate(frame, [0, 0.4 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 0.5 * fps, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = fadeIn * fadeOut;

  // ── Dot wave entrance ──
  const dotWaveProgress = interpolate(frame, [0, 1.2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Title entrance ──
  const titleSpring = spring({
    frame,
    fps,
    delay: Math.round(0.15 * fps),
    config: { damping: 24, stiffness: 110 },
    durationInFrames: Math.round(0.8 * fps),
  });
  const titleY = interpolate(titleSpring, [0, 1], [30, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Body text entrance ──
  const bodySpring = spring({
    frame,
    fps,
    delay: Math.round(0.35 * fps),
    config: { damping: 22, stiffness: 100 },
    durationInFrames: Math.round(0.8 * fps),
  });
  const bodyY = interpolate(bodySpring, [0, 1], [25, 0]);
  const bodyOpacity = interpolate(bodySpring, [0, 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Image entrance ──
  const imgSpring = spring({
    frame,
    fps,
    delay: Math.round(0.2 * fps),
    config: { damping: 18, stiffness: 100 },
    durationInFrames: Math.round(1 * fps),
  });
  const imgScale = interpolate(imgSpring, [0, 1], [0.85, 1]);
  const imgOpacity = interpolate(imgSpring, [0, 0.4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Bottom decorations entrance ──
  const decoSpring = spring({
    frame,
    fps,
    delay: Math.round(0.6 * fps),
    config: { damping: 16, stiffness: 90 },
    durationInFrames: Math.round(0.8 * fps),
  });
  const decoScale = interpolate(decoSpring, [0, 1], [0, 1]);
  const decoOpacity = interpolate(decoSpring, [0, 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Parse text for bullet points ──
  const blocks = parseTextBlocks(text);

  const hasIllustration = Boolean(illustration_url);
  const isImageLeft = layout === "image-left";

  // ── Accent line under title ──
  const accentLineWidth = interpolate(titleSpring, [0, 1], [0, 80]);

  // ── Text side ──
  const textSide = (
    <div
      style={{
        width: hasIllustration ? "50%" : "100%",
        maxWidth: hasIllustration ? undefined : 1240,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        margin: hasIllustration ? undefined : "0 auto",
        padding: hasIllustration
          ? isImageLeft
            ? "0 36px 0 0"
            : "0 0 0 40px"
          : "0 40px",
      }}
    >
      {/* Title */}
      {title && (
        <div
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            marginBottom: 8,
          }}
        >
          <div
            style={{
              fontSize: hasIllustration ? 54 : 60,
              fontWeight: 800,
              fontFamily: theme.font.sans,
              color: titleColor,
              lineHeight: 1.2,
              letterSpacing: -0.3,
            }}
          >
            {title}
          </div>
          <div
            style={{
              width: accentLineWidth,
              height: 4,
              backgroundColor: accent_color,
              borderRadius: 2,
              marginTop: 14,
              marginBottom: 10,
            }}
          />
        </div>
      )}

      {/* Body text / bullet points */}
      <div
        style={{
          opacity: bodyOpacity,
          transform: `translateY(${bodyY}px)`,
        }}
      >
        {blocks.map((block, i) => {
          const bulletDelay = Math.round((0.4 + i * 0.08) * fps);
          const bulletSpring = spring({
            frame,
            fps,
            delay: bulletDelay,
            config: { damping: 22, stiffness: 110 },
            durationInFrames: Math.round(0.6 * fps),
          });
          const bulletX = interpolate(bulletSpring, [0, 1], [-20, 0]);
          const bulletOpacity = interpolate(bulletSpring, [0, 0.4], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          if (block.type === "bullet") {
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  marginBottom: 20,
                  opacity: bulletOpacity,
                  transform: `translateX(${bulletX}px)`,
                }}
              >
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    backgroundColor: accent_color,
                    marginTop: 14,
                    marginRight: 18,
                    flexShrink: 0,
                  }}
                />
                <div
                style={{
                    fontSize: hasIllustration ? 32 : 36,
                    fontWeight: 600,
                    fontFamily: theme.font.sans,
                    color: bodyColor,
                    lineHeight: 1.55,
                  }}
                >
                  {renderHighlightedText(
                    block.content,
                    highlighted_keywords,
                    resolvedHighlightColor,
                    bodyColor,
                  )}
                </div>
              </div>
            );
          }

          return (
            <div
              key={i}
              style={{
                fontSize: hasIllustration ? 34 : 38,
                fontWeight: 600,
                fontFamily: theme.font.sans,
                color: bodyColor,
                lineHeight: 1.55,
                marginBottom: 22,
                opacity: bulletOpacity,
                transform: `translateX(${bulletX}px)`,
              }}
            >
              {renderHighlightedText(
                block.content,
                highlighted_keywords,
                resolvedHighlightColor,
                bodyColor,
              )}
            </div>
          );
        })}
      </div>
    </div>
  );

  // ── Image side ──
  const imageSide = hasIllustration ? (
    <div
      style={{
        width: "50%",
        height: "100%",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        opacity: imgOpacity,
        transform: `translateY(${interpolate(imgSpring, [0, 1], [24, 0])}px) scale(${imgScale})`,
      }}
    >
      <div
        style={{
          position: "relative",
          width: "92%",
          height: "76%",
          borderRadius: 28,
          overflow: "hidden",
          backgroundColor: "#FFFFFF",
          boxShadow: `0 18px 50px ${hexToRgba(accent_color, 0.18)}, 0 8px 20px rgba(15, 26, 48, 0.12)`,
          border: `2px solid ${hexToRgba(accent_color, 0.18)}`,
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `linear-gradient(180deg, ${hexToRgba(accent_color, 0.03)} 0%, rgba(255,255,255,0) 28%)`,
            zIndex: 1,
            pointerEvents: "none",
          }}
        />
        <Img
          src={
            illustration_url!.startsWith("http")
              ? illustration_url!
              : staticFile(illustration_url!)
          }
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
          }}
        />
      </div>
    </div>
  ) : null;

  // ── Decoration data ──
  const crosses = [
    { x: 180, y: 920, size: 28, rot: 0 },
    { x: 420, y: 960, size: 18, rot: 15 },
    { x: 900, y: 940, size: 24, rot: -10 },
    { x: 1350, y: 960, size: 20, rot: 8 },
    { x: 1620, y: 920, size: 26, rot: -5 },
  ];
  const diamonds = [
    { x: 300, y: 950, size: 7 },
    { x: 650, y: 970, size: 5 },
    { x: 1100, y: 935, size: 6 },
    { x: 1500, y: 955, size: 8 },
    { x: 1750, y: 940, size: 5 },
  ];

  return (
    <AbsoluteFill style={{ opacity }}>
      {/* Background */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(170deg, ${bgBase} 0%, ${bgTint} 60%, ${lighten(accent_color, 0.9)} 100%)`,
        }}
      />

      {/* Animated floating shapes */}
      <FloatingBackground accent={accent_color} frame={frame} fps={fps} />

      {/* Subtle side accent glow */}
      <div
        style={{
          position: "absolute",
          top: "20%",
          right: isImageLeft ? undefined : "-5%",
          left: isImageLeft ? "-5%" : undefined,
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${hexToRgba(accent_color, 0.06)} 0%, transparent 70%)`,
        }}
      />

      {/* Dot wave at top */}
      <DotWave accent={accent_color} progress={dotWaveProgress} width={1760} />

      {/* Content layout */}
      <div
        style={{
          position: "absolute",
          top: 100,
          left: 100,
          right: 100,
          bottom: 100,
          display: "flex",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: hasIllustration ? "space-between" : "center",
          gap: hasIllustration ? 28 : 0,
        }}
      >
        {isImageLeft ? (
          <>
            {imageSide}
            {textSide}
          </>
        ) : (
          <>
            {textSide}
            {imageSide}
          </>
        )}
      </div>

      {/* Bottom decorative crosses */}
      {crosses.map((c, i) => (
        <AccentCross
          key={`cross-${i}`}
          x={c.x}
          y={c.y}
          size={c.size}
          color={hexToRgba(accent_color, 0.18 + seededRand(i + 50) * 0.12)}
          opacity={decoOpacity}
          rotation={c.rot}
          scale={decoScale}
        />
      ))}

      {/* Bottom decorative diamonds */}
      {diamonds.map((d, i) => (
        <AccentDiamond
          key={`diamond-${i}`}
          x={d.x}
          y={d.y}
          size={d.size}
          color={hexToRgba(accent_color, 0.15 + seededRand(i + 30) * 0.15)}
          opacity={decoOpacity}
          scale={decoScale}
        />
      ))}

      {/* Bottom accent line */}
      <div
        style={{
          position: "absolute",
          bottom: 50,
          left: "50%",
          transform: `translateX(-50%) scaleX(${decoScale})`,
          width: 120,
          height: 3,
          borderRadius: 2,
          backgroundColor: hexToRgba(accent_color, 0.25),
          opacity: decoOpacity,
        }}
      />
    </AbsoluteFill>
  );
};
