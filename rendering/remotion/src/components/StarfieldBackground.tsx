import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "../design/theme";

// ── Types ───────────────────────────────────────────────────

export interface StarfieldBackgroundProps {
  particle_count?: number;
  drift_speed?: number;
  color?: string;
  gradient_start?: string;
  gradient_end?: string;
  seed?: number;
}

// ── Deterministic PRNG (mulberry32) ─────────────────────────

function mulberry32(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ── Particle generation ─────────────────────────────────────

interface Particle {
  x: number;
  y: number;
  size: number;
  baseOpacity: number;
  twinkleSpeed: number;
  twinklePhase: number;
  driftAngle: number;
  driftRadius: number;
}

function generateParticles(count: number, seed: number): Particle[] {
  const rng = mulberry32(seed);
  const particles: Particle[] = [];
  for (let i = 0; i < count; i++) {
    particles.push({
      x: rng() * 100,
      y: rng() * 100,
      size: 1 + rng() * 2.5,
      baseOpacity: 0.2 + rng() * 0.6,
      twinkleSpeed: 0.3 + rng() * 0.7,
      twinklePhase: rng() * Math.PI * 2,
      driftAngle: rng() * Math.PI * 2,
      driftRadius: 0.2 + rng() * 0.6,
    });
  }
  return particles;
}

// ── Component ───────────────────────────────────────────────

export const StarfieldBackground: React.FC<StarfieldBackgroundProps> = ({
  particle_count = 30,
  drift_speed = 1,
  color = "#FFFFFF",
  gradient_start = theme.bg,
  gradient_end = theme.surface,
  seed = 42,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const particles = React.useMemo(
    () => generateParticles(particle_count, seed),
    [particle_count, seed],
  );

  const timeSec = frame / fps;

  return (
    <AbsoluteFill>
      {/* Dark gradient base */}
      <div
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          background: `radial-gradient(ellipse 80% 70% at 50% 40%, ${gradient_end} 0%, ${gradient_start} 100%)`,
        }}
      />

      {/* Particles */}
      {particles.map((p, i) => {
        const twinkle =
          0.5 +
          0.5 *
            Math.sin(
              timeSec * p.twinkleSpeed * Math.PI * 2 + p.twinklePhase,
            );
        const opacity = p.baseOpacity * twinkle;

        const driftX =
          Math.cos(timeSec * drift_speed * 0.3 + p.driftAngle) *
          p.driftRadius;
        const driftY =
          Math.sin(timeSec * drift_speed * 0.3 + p.driftAngle) *
          p.driftRadius;

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${p.x + driftX}%`,
              top: `${p.y + driftY}%`,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              backgroundColor: color,
              opacity,
              boxShadow: `0 0 ${p.size * 2}px ${color}40`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
