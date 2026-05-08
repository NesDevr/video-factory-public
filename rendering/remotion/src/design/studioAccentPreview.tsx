import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getRemotionEnvironment } from "remotion";
import demoChannelConfig from "../../../../config/channels/demo_channel.json";

type ChannelConfig = {
  style: {
    text: {
      title_accent_color?: string;
      section_color_palette?: string[] | null;
    };
  };
};

type PreviewTheme = {
  id: string;
  label: string;
  colors: string[];
};

type PaletteSection = {
  id: string;
  label: string;
  colors: string[];
};

export type ColorTargetDescriptor<P extends object> = {
  id: string;
  label: string;
  get: (props: P) => string | null;
  set: (props: P, color: string) => P;
  isVisible?: (props: P) => boolean;
};

const CHANNEL_PREVIEW_THEMES: PreviewTheme[] = [
  {
    id: "demo_channel",
    label: "Demo Channel",
    colors: collectThemeColors(demoChannelConfig),
  },
];

const SPECTRUM_HUES = [0, 28, 52, 88, 120, 148, 182, 208, 242, 270, 300, 326];
const SPECTRUM_LIGHTNESS = [88, 78, 68, 58, 48, 38, 28, 18];
const SPECTRUM_SATURATION = 92;
const GRAYSCALE_VALUES = [244, 222, 196, 168, 140, 112, 80, 20];
const SPECTRUM_COLUMNS = SPECTRUM_HUES.length + 1;

function collectThemeColors(config: ChannelConfig): string[] {
  const rawColors = [
    config.style.text.title_accent_color,
    ...(config.style.text.section_color_palette ?? []),
  ].filter((color): color is string => Boolean(color));

  return rawColors.filter((color, index) => rawColors.indexOf(color) === index);
}

function uniqueColors(colors: readonly string[]): string[] {
  return colors.filter((color, index) => colors.indexOf(color) === index);
}

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const s = saturation / 100;
  const l = lightness / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = l - c / 2;

  let r = 0;
  let g = 0;
  let b = 0;

  if (hue < 60) {
    r = c;
    g = x;
  } else if (hue < 120) {
    r = x;
    g = c;
  } else if (hue < 180) {
    g = c;
    b = x;
  } else if (hue < 240) {
    g = x;
    b = c;
  } else if (hue < 300) {
    r = x;
    b = c;
  } else {
    r = c;
    b = x;
  }

  const toHex = (value: number) =>
    Math.round((value + m) * 255)
      .toString(16)
      .padStart(2, "0")
      .toUpperCase();

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function grayscaleHex(value: number): string {
  const hex = value.toString(16).padStart(2, "0").toUpperCase();
  return `#${hex}${hex}${hex}`;
}

function buildSpectrumPalette(): string[] {
  const colors: string[] = [];

  SPECTRUM_LIGHTNESS.forEach((lightness, rowIndex) => {
    for (const hue of SPECTRUM_HUES) {
      colors.push(hslToHex(hue, SPECTRUM_SATURATION, lightness));
    }
    colors.push(grayscaleHex(GRAYSCALE_VALUES[rowIndex] ?? 244));
  });

  return colors;
}

const PICKER_SECTIONS: readonly PaletteSection[] = [
  {
    id: "channel_swatches",
    label: "Channel Swatches",
    colors: uniqueColors(CHANNEL_PREVIEW_THEMES.flatMap((theme) => theme.colors)),
  },
  {
    id: "spectrum",
    label: "Spectrum",
    colors: buildSpectrumPalette(),
  },
];

function normalizeHexColor(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }

  const raw = trimmed.startsWith("#") ? trimmed.slice(1) : trimmed;
  if (!/^[0-9a-fA-F]{6}$/.test(raw)) {
    return null;
  }

  return `#${raw.toUpperCase()}`;
}

function applyColorOverrides<P extends object>(
  props: P,
  targets: readonly ColorTargetDescriptor<P>[],
  overrides: Readonly<Record<string, string>>,
): P {
  let nextProps = props;

  for (const target of targets) {
    const color = overrides[target.id];
    if (!color) {
      continue;
    }

    nextProps = target.set(nextProps, color);
  }

  return nextProps;
}

function removeOverride(
  overrides: Readonly<Record<string, string>>,
  targetId: string,
): Record<string, string> {
  const next = { ...overrides };
  delete next[targetId];
  return next;
}

export function accentColorTarget<P extends { accent_color?: string }>(
  defaultColor: string,
  label = "Accent",
): ColorTargetDescriptor<P> {
  return {
    id: "accent_color",
    label,
    get: (props) => props.accent_color ?? defaultColor,
    set: (props, color) => ({ ...props, accent_color: color }),
  };
}

export function withStudioAccentPreview<P extends object>(
  Component: React.ComponentType<P>,
  targets: readonly ColorTargetDescriptor<P>[],
) {
  const WrappedComponent: React.FC<P> = (props) => {
    const isStudio = getRemotionEnvironment().isStudio;
    const [overrides, setOverrides] = useState<Record<string, string>>({});
    const [activeTargetId, setActiveTargetId] = useState<string | null>(null);
    const [pickerOpen, setPickerOpen] = useState(false);
    const [draftHex, setDraftHex] = useState("");
    const nativeColorInputRef = useRef<HTMLInputElement>(null);

    const visibleTargets = useMemo(
      () =>
        targets.filter((target) =>
          target.isVisible ? target.isVisible(props) : target.get(props) !== null,
        ),
      [props, targets],
    );

    const resolvedProps = useMemo(
      () =>
        isStudio
          ? applyColorOverrides(props, targets, overrides)
          : props,
      [isStudio, overrides, props, targets],
    );

    useEffect(() => {
      if (visibleTargets.length === 0) {
        setActiveTargetId(null);
        return;
      }

      if (activeTargetId && visibleTargets.some((target) => target.id === activeTargetId)) {
        return;
      }

      setActiveTargetId(visibleTargets[0].id);
    }, [activeTargetId, visibleTargets]);

    const activeTarget =
      visibleTargets.find((target) => target.id === activeTargetId) ?? null;
    const activeColor = activeTarget ? activeTarget.get(resolvedProps) : null;
    const draftHexNormalized = normalizeHexColor(draftHex);
    const draftHexHasError = draftHex.length > 0 && draftHexNormalized === null;

    useEffect(() => {
      setDraftHex(activeColor ?? "");
    }, [activeColor, activeTargetId]);

    const setTargetColor = useCallback((targetId: string, color: string) => {
      setOverrides((current) => ({
        ...current,
        [targetId]: color,
      }));
    }, []);

    const handleSwatchClick = useCallback((color: string) => {
      if (!activeTarget) {
        return;
      }

      setTargetColor(activeTarget.id, color);
      setDraftHex(color);
    }, [activeTarget, setTargetColor]);

    const handleHexChange = useCallback((value: string) => {
      const nextValue = value.toUpperCase();
      setDraftHex(nextValue);

      if (!activeTarget) {
        return;
      }

      const normalized = normalizeHexColor(nextValue);
      if (normalized) {
        setTargetColor(activeTarget.id, normalized);
      }
    }, [activeTarget, setTargetColor]);

    const handleHexBlur = useCallback(() => {
      setDraftHex(activeColor ?? "");
    }, [activeColor]);

    const handleBrowserPickerClick = useCallback(() => {
      nativeColorInputRef.current?.click();
    }, []);

    const handleBrowserPickerChange = useCallback((value: string) => {
      const normalized = normalizeHexColor(value);
      if (!normalized || !activeTarget) {
        return;
      }

      setTargetColor(activeTarget.id, normalized);
      setDraftHex(normalized);
    }, [activeTarget, setTargetColor]);

    const handleCopyHex = useCallback(() => {
      if (!activeColor) {
        return;
      }

      void navigator.clipboard.writeText(activeColor.toUpperCase());
    }, [activeColor]);

    const handleResetTarget = useCallback(() => {
      if (!activeTarget) {
        return;
      }

      setOverrides((current) => removeOverride(current, activeTarget.id));
    }, [activeTarget]);

    const handleResetAll = useCallback(() => {
      setOverrides({});
    }, []);

    if (!isStudio || visibleTargets.length === 0) {
      return <Component {...props} />;
    }

    return (
      <>
        <Component {...resolvedProps} />
        <div
          style={{
            position: "absolute",
            top: 28,
            right: 28,
            zIndex: 1000,
            width: 344,
            padding: "16px 18px",
            borderRadius: 18,
            backgroundColor: "rgba(10, 14, 26, 0.9)",
            border: "1px solid rgba(255,255,255,0.12)",
            boxShadow: "0 18px 50px rgba(0,0,0,0.35)",
            color: "#FFFFFF",
            fontFamily: "Inter, Arial, sans-serif",
            backdropFilter: "blur(14px)",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.5, opacity: 0.75 }}>
            COLOR PREVIEW
          </div>
          <div style={{ marginTop: 6, fontSize: 18, fontWeight: 700 }}>
            Studio palette controls
          </div>
          <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, opacity: 0.72 }}>
            Pick which color prop to edit, then apply a channel swatch or exact hex.
          </div>

          {visibleTargets.length > 1 ? (
            <div style={{ marginTop: 14 }}>
              <div style={{ marginBottom: 8, fontSize: 12, fontWeight: 700, opacity: 0.78 }}>
                Target
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {visibleTargets.map((target) => {
                  const isActive = target.id === activeTarget?.id;
                  return (
                    <button
                      key={target.id}
                      type="button"
                      onClick={() => setActiveTargetId(target.id)}
                      style={{
                        borderRadius: 999,
                        border: isActive
                          ? "1px solid rgba(255,255,255,0.3)"
                          : "1px solid rgba(255,255,255,0.14)",
                        backgroundColor: isActive
                          ? "rgba(255,255,255,0.14)"
                          : "rgba(255,255,255,0.06)",
                        color: "#FFFFFF",
                        padding: "8px 12px",
                        fontSize: 12,
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      {target.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div style={{ marginTop: 14 }}>
            <div style={{ marginBottom: 8, fontSize: 12, fontWeight: 700, opacity: 0.78 }}>
              Picker
            </div>
            <button
              type="button"
              onClick={() => setPickerOpen((open) => !open)}
              style={{
                width: "100%",
                borderRadius: 14,
                border: "1px solid rgba(255,255,255,0.14)",
                backgroundColor: "rgba(255,255,255,0.06)",
                color: "#FFFFFF",
                padding: "10px 12px",
                fontSize: 13,
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <span>{pickerOpen ? "Hide Picker" : "Open Picker"}</span>
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontFamily: "'JetBrains Mono', 'Courier New', monospace",
                  fontSize: 12,
                }}
              >
                <span
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 999,
                    backgroundColor: activeColor ?? "#FFFFFF",
                    border: "1px solid rgba(255,255,255,0.18)",
                    flexShrink: 0,
                  }}
                />
                <span>{activeColor ? activeColor.toUpperCase() : ""}</span>
              </span>
            </button>

            {pickerOpen ? (
              <div
                style={{
                  marginTop: 10,
                  borderRadius: 16,
                  border: "1px solid rgba(255,255,255,0.1)",
                  backgroundColor: "rgba(255,255,255,0.04)",
                  padding: 12,
                }}
              >
                <input
                  ref={nativeColorInputRef}
                  type="color"
                  value={activeColor ?? "#FFFFFF"}
                  onChange={(event) => handleBrowserPickerChange(event.currentTarget.value)}
                  style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
                  tabIndex={-1}
                />

                <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                  <button
                    type="button"
                    onClick={handleBrowserPickerClick}
                    style={{
                      ...actionButtonStyle,
                      flex: 1,
                    }}
                  >
                    Browser Picker
                  </button>
                  <button
                    type="button"
                    onClick={() => setPickerOpen(false)}
                    style={{
                      ...actionButtonStyle,
                      flex: 1,
                    }}
                  >
                    Close
                  </button>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {PICKER_SECTIONS.map((section) => (
                    <div key={section.id}>
                      <div
                        style={{
                          marginBottom: 8,
                          fontSize: 12,
                          fontWeight: 700,
                          opacity: 0.78,
                        }}
                      >
                        {section.label}
                      </div>
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns:
                            section.id === "spectrum"
                              ? `repeat(${SPECTRUM_COLUMNS}, minmax(0, 1fr))`
                              : "repeat(auto-fill, minmax(24px, 1fr))",
                          gap: 6,
                        }}
                      >
                        {section.colors.map((color) => {
                          const isActive =
                            activeColor?.toUpperCase() === color.toUpperCase();

                          return (
                            <button
                              key={`${section.id}-${color}`}
                              type="button"
                              title={color}
                              onClick={() => handleSwatchClick(color)}
                              style={{
                                width: "100%",
                                minWidth: 24,
                                aspectRatio: "1 / 1",
                                borderRadius: section.id === "spectrum" ? 6 : 999,
                                border: isActive
                                  ? "2px solid #FFFFFF"
                                  : "1px solid rgba(255,255,255,0.18)",
                                backgroundColor: color,
                                boxShadow: isActive
                                  ? "0 0 0 2px rgba(255,255,255,0.18)"
                                  : "none",
                                cursor: "pointer",
                                padding: 0,
                              }}
                            />
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{ marginTop: 12 }}>
                  <div style={{ marginBottom: 8, fontSize: 12, fontWeight: 700, opacity: 0.78 }}>
                    Exact hex
                  </div>
                  <input
                    type="text"
                    value={draftHex}
                    onChange={(event) => handleHexChange(event.currentTarget.value)}
                    onBlur={handleHexBlur}
                    spellCheck={false}
                    placeholder="#RRGGBB"
                    style={{
                      width: "100%",
                      borderRadius: 12,
                      border: draftHexHasError
                        ? "1px solid rgba(255, 120, 120, 0.9)"
                        : "1px solid rgba(255,255,255,0.14)",
                      backgroundColor: "rgba(255,255,255,0.06)",
                      color: "#FFFFFF",
                      padding: "10px 12px",
                      fontSize: 14,
                      fontWeight: 700,
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                  <div
                    style={{
                      marginTop: 6,
                      fontSize: 11,
                      opacity: draftHexHasError ? 0.95 : 0.62,
                    }}
                  >
                    {draftHexHasError
                      ? "Use a 6-digit hex like #2E86DE."
                      : "Preview updates only when the hex is valid."}
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <div
            style={{
              marginTop: 14,
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
            }}
          >
            <button
              type="button"
              onClick={handleCopyHex}
              style={actionButtonStyle}
            >
              Copy Hex
            </button>
            <button
              type="button"
              onClick={handleResetTarget}
              style={actionButtonStyle}
            >
              Reset Target
            </button>
            <button
              type="button"
              onClick={handleResetAll}
              style={{
                ...actionButtonStyle,
                gridColumn: "1 / span 2",
              }}
            >
              Reset All
            </button>
          </div>

          <div
            style={{
              marginTop: 14,
              paddingTop: 12,
              borderTop: "1px solid rgba(255,255,255,0.1)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 12,
              opacity: 0.82,
            }}
          >
            <span>{activeTarget?.label ?? "No target"}</span>
            <span style={{ fontFamily: "'JetBrains Mono', 'Courier New', monospace" }}>
              {activeColor ? activeColor.toUpperCase() : ""}
            </span>
          </div>
        </div>
      </>
    );
  };

  WrappedComponent.displayName = `withStudioAccentPreview(${Component.displayName ?? Component.name ?? "Component"})`;

  return WrappedComponent;
}

const actionButtonStyle: React.CSSProperties = {
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.14)",
  backgroundColor: "rgba(255,255,255,0.06)",
  color: "#FFFFFF",
  padding: "10px 12px",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};
