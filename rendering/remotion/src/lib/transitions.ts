import type React from "react";

export interface TransitionStyles {
  entering: React.CSSProperties;
  exiting: React.CSSProperties;
}

/**
 * Crossfade: incoming fades in over the outgoing slot.
 * The outgoing slot stays at full opacity underneath — since layers are
 * stacked (not composited), fading both would reveal the black background.
 */
export function fade(progress: number): TransitionStyles {
  return {
    entering: { opacity: progress },
    exiting: {},
  };
}

/**
 * Wipe left: incoming slides in from the right via clipPath.
 */
export function wipeleft(progress: number): TransitionStyles {
  const pct = progress * 100;
  return {
    entering: { clipPath: `inset(0 0 0 ${100 - pct}%)` },
    exiting: {},
  };
}

/**
 * Hard cut: no overlap, no animation. Transition duration should be 0.
 */
export function cut(): TransitionStyles {
  return {
    entering: {},
    exiting: {},
  };
}

const TRANSITIONS: Record<string, (p: number) => TransitionStyles> = {
  fade,
  wipeleft,
  cut: () => cut(),
};

export function getTransition(
  type: string,
  progress: number,
): TransitionStyles {
  const fn = TRANSITIONS[type] ?? fade;
  return fn(progress);
}
