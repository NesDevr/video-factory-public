import { interpolate, spring } from "remotion";

/**
 * Smooth draw-in progress (0 → 1) over a given number of frames,
 * using a spring with high damping for a clean deceleration.
 */
export function drawInProgress(
  frame: number,
  fps: number,
  durationFrames: number,
): number {
  return spring({
    frame,
    fps,
    config: { damping: 200 },
    durationInFrames: durationFrames,
  });
}

/**
 * Fade-in opacity from 0 to 1 over the given frame range.
 */
export function fadeIn(
  frame: number,
  startFrame: number,
  durationFrames: number,
): number {
  return interpolate(frame, [startFrame, startFrame + durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

/**
 * Map a normalized value (0–1) to a pixel range for SVG path drawing.
 */
export function pathProgress(
  progress: number,
  totalLength: number,
): { strokeDasharray: number; strokeDashoffset: number } {
  return {
    strokeDasharray: totalLength,
    strokeDashoffset: totalLength * (1 - progress),
  };
}
