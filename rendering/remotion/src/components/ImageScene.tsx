import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  Img,
  staticFile,
} from "remotion";

export interface ImageSceneProps {
  image_path: string;
  animation_preset?: string;
  direction?: string;
}

/**
 * Animated still-image component with multiple motion presets.
 * Replaces Ken Burns FFmpeg filter for channels with animated_clips enabled.
 *
 * All presets keep the image fully visible from frame 0 — no black frames.
 *
 * Presets:
 *  - "parallax"   — slow pan with slight scale, creating depth illusion
 *  - "drift"      — gentle diagonal drift with rotation
 *  - "zoom_focus" — slow zoom from wide to tight center crop
 */
export const ImageScene: React.FC<ImageSceneProps> = ({
  image_path,
  animation_preset = "parallax",
  direction = "left",
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Normalize progress 0 → 1 over the full clip duration
  const progress = frame / Math.max(durationInFrames - 1, 1);

  const style = getPresetStyle(animation_preset, direction, progress);

  // Image must be placed in Remotion's public/ dir before rendering.
  const src = staticFile(image_path);

  return (
    <AbsoluteFill>
      <Img
        src={src}
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transformOrigin: "center center",
          ...style,
        }}
      />
    </AbsoluteFill>
  );
};

function getPresetStyle(
  preset: string,
  direction: string,
  progress: number,
): React.CSSProperties {
  switch (preset) {
    case "parallax":
      return parallaxStyle(direction, progress);
    case "drift":
      return driftStyle(direction, progress);
    case "zoom_focus":
      return zoomFocusStyle(progress);
    default:
      return parallaxStyle(direction, progress);
  }
}

/**
 * Parallax: slow pan across the image with slight scale for depth.
 * Scale ensures the image always covers the frame even at max translate.
 */
function parallaxStyle(direction: string, progress: number): React.CSSProperties {
  const scale = 1.2;
  const travel = 5; // percent — kept under (scale-1)/2 so edges never show
  const eased = easeInOut(progress);

  let tx = 0;
  let ty = 0;
  switch (direction) {
    case "left":
      tx = interpolateLinear(eased, travel, -travel);
      break;
    case "right":
      tx = interpolateLinear(eased, -travel, travel);
      break;
    case "up":
      ty = interpolateLinear(eased, travel, -travel);
      break;
    case "down":
      ty = interpolateLinear(eased, -travel, travel);
      break;
  }

  return {
    transform: `scale(${scale}) translate(${tx}%, ${ty}%)`,
  };
}

/**
 * Drift: gentle diagonal movement with subtle rotation.
 * Creates an organic, documentary-like motion feel.
 */
function driftStyle(direction: string, progress: number): React.CSSProperties {
  const scale = 1.15;
  const eased = easeInOut(progress);

  let tx: number;
  let ty: number;
  let rot: number;

  switch (direction) {
    case "left":
      tx = interpolateLinear(eased, 3, -3);
      ty = interpolateLinear(eased, -1.5, 1.5);
      rot = interpolateLinear(eased, 0.5, -0.5);
      break;
    case "right":
      tx = interpolateLinear(eased, -3, 3);
      ty = interpolateLinear(eased, 1.5, -1.5);
      rot = interpolateLinear(eased, -0.5, 0.5);
      break;
    case "up":
      tx = interpolateLinear(eased, 1.5, -1.5);
      ty = interpolateLinear(eased, 3, -3);
      rot = interpolateLinear(eased, -0.3, 0.3);
      break;
    case "down":
    default:
      tx = interpolateLinear(eased, -1.5, 1.5);
      ty = interpolateLinear(eased, -3, 3);
      rot = interpolateLinear(eased, 0.3, -0.3);
      break;
  }

  return {
    transform: `scale(${scale}) translate(${tx}%, ${ty}%) rotate(${rot}deg)`,
  };
}

/**
 * Zoom focus: slow zoom from wide to tight center crop.
 * Image is always fully visible — just the crop level changes.
 */
function zoomFocusStyle(progress: number): React.CSSProperties {
  const eased = easeInOut(progress);
  const scale = interpolateLinear(eased, 1.25, 1.05);

  return {
    transform: `scale(${scale})`,
  };
}

// --- Easing helpers ---

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}

function interpolateLinear(t: number, from: number, to: number): number {
  return from + (to - from) * t;
}
