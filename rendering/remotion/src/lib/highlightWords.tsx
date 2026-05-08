import React from "react";

/**
 * Strip punctuation from word edges for case-insensitive keyword matching.
 * "output," -> "output", "review." -> "review"
 */
function stripPunct(word: string): string {
  return word.replace(/^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$/g, "");
}

/**
 * Render text with highlighted keywords.
 * Matched words get `highlightColor`; unmatched stay `baseColor`.
 */
export function renderHighlightedText(
  text: string,
  keywords: string[],
  highlightColor: string,
  baseColor: string = "#FFFFFF",
): React.ReactNode {
  if (!keywords || keywords.length === 0) {
    return text;
  }

  // Split multi-word keywords (e.g. "final review") into individual words
  // so each word in the phrase gets highlighted independently.
  const keywordSet = new Set(
    keywords.flatMap((k) => k.toLowerCase().split(/\s+/)),
  );

  return text.split(" ").map((word, i) => {
    const stripped = stripPunct(word).toLowerCase();
    const isHighlighted = keywordSet.has(stripped);
    return (
      <React.Fragment key={i}>
        {i > 0 && " "}
        <span style={{ color: isHighlighted ? highlightColor : baseColor }}>
          {word}
        </span>
      </React.Fragment>
    );
  });
}
