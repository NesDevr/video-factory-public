import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { theme } from "../design/theme";
import { renderHighlightedText } from "../lib/highlightWords";

// ── Types ───────────────────────────────────────────────────

export interface WordTimestamp {
  word: string;
  start: number;
  end: number;
}

export interface NarrationSubtitleProps {
  word_timestamps: WordTimestamp[];
  highlighted_keywords?: string[];
  highlight_color?: string;
  /** Frame ranges [start, end] where subtitles should be hidden (e.g. during chart slots). */
  suppress_frame_ranges?: [number, number][];
}

interface Phrase {
  text: string;
  startSec: number;
  endSec: number;
}

// ── Phrase grouping ─────────────────────────────────────────

const PHRASE_MIN_WORDS = 4;
const PHRASE_MAX_WORDS = 8;
const GAP_THRESHOLD_SEC = 0.35;
const PUNCTUATION_RE = /[.!?,;:—–\-]/;

function groupIntoPhrases(words: WordTimestamp[]): Phrase[] {
  if (words.length === 0) return [];

  const phrases: Phrase[] = [];
  let buf: WordTimestamp[] = [words[0]];

  for (let i = 1; i < words.length; i++) {
    const prev = words[i - 1];
    const cur = words[i];

    const gap = cur.start - prev.end;
    const prevEndsWithPunct = PUNCTUATION_RE.test(prev.word.slice(-1));
    const atMax = buf.length >= PHRASE_MAX_WORDS;
    const atMinAndBreak =
      buf.length >= PHRASE_MIN_WORDS &&
      (gap > GAP_THRESHOLD_SEC || prevEndsWithPunct);

    if (atMax || atMinAndBreak) {
      phrases.push({
        text: buf.map((w) => w.word).join(" "),
        startSec: buf[0].start,
        endSec: buf[buf.length - 1].end,
      });
      buf = [cur];
    } else {
      buf.push(cur);
    }
  }

  // Flush remaining
  if (buf.length > 0) {
    phrases.push({
      text: buf.map((w) => w.word).join(" "),
      startSec: buf[0].start,
      endSec: buf[buf.length - 1].end,
    });
  }

  return phrases;
}

// ── Component ───────────────────────────────────────────────

const FADE_FRAMES = 4;

export const NarrationSubtitle: React.FC<NarrationSubtitleProps> = ({
  word_timestamps,
  highlighted_keywords = [],
  highlight_color = "#FFD600",
  suppress_frame_ranges = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const phrases = React.useMemo(
    () => groupIntoPhrases(word_timestamps ?? []),
    [word_timestamps],
  );

  // Hide subtitles during full-screen component slots (charts, CTA, etc.)
  const isSuppressed = suppress_frame_ranges.some(
    ([start, end]) => frame >= start && frame < end,
  );
  if (isSuppressed) return null;

  const currentSec = frame / fps;

  // Find the active phrase — the one whose time window contains currentSec
  const activeIdx = phrases.findIndex(
    (p) => currentSec >= p.startSec && currentSec <= p.endSec,
  );

  if (activeIdx === -1) return null;

  const phrase = phrases[activeIdx];

  // Compute phrase-local frame for entrance animation
  const phraseStartFrame = Math.round(phrase.startSec * fps);
  const phraseEndFrame = Math.round(phrase.endSec * fps);
  const phraseDuration = phraseEndFrame - phraseStartFrame;
  const phraseLocalFrame = frame - phraseStartFrame;

  // Spring entrance
  const enterSpring = spring({
    frame: phraseLocalFrame,
    fps,
    config: { damping: 28, stiffness: 180 },
    durationInFrames: FADE_FRAMES * 2,
  });

  // Fade out near phrase end
  const fadeOut = interpolate(
    phraseLocalFrame,
    [Math.max(phraseDuration - FADE_FRAMES, 0), phraseDuration],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const opacity = enterSpring * fadeOut;
  const translateY = interpolate(enterSpring, [0, 1], [12, 0]);

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 100,
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px)`,
          textAlign: "center",
          maxWidth: "85%",
          color: "#FFFFFF",
          fontSize: 58,
          fontWeight: 800,
          fontFamily: theme.font.sans,
          lineHeight: 1.25,
          letterSpacing: 0.5,
          textTransform: "uppercase",
          // Stroke via text-shadow stack: 4-direction outline + drop shadow
          textShadow: [
            // Outline (thick)
            "-2px -2px 0 #000",
            "2px -2px 0 #000",
            "-2px 2px 0 #000",
            "2px 2px 0 #000",
            // Softer glow
            "0 0 8px rgba(0,0,0,0.9)",
            "0 0 20px rgba(0,0,0,0.6)",
            // Drop shadow
            "0 4px 12px rgba(0,0,0,0.8)",
          ].join(", "),
        }}
      >
        {renderHighlightedText(phrase.text, highlighted_keywords, highlight_color)}
      </div>
    </AbsoluteFill>
  );
};
