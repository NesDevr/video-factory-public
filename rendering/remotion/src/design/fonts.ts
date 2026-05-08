import { staticFile } from "remotion";

/**
 * Font loading for Remotion compositions.
 *
 * We rely on system fonts (Inter, JetBrains Mono) with fallbacks.
 * If custom font files are needed later, place them in public/fonts/
 * and load them here with @font-face via staticFile().
 */
export function loadFonts(): void {
  // No-op for now — using system font stack from theme.ts
  // Add @font-face declarations here if bundling custom fonts.
}
