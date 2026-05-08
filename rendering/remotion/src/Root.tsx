import type { ComponentType } from "react";
import { Composition, Folder, staticFile, type CalculateMetadataFunction } from "remotion";
import { AnimatedLineChart, type LineChartProps } from "./components/AnimatedLineChart";
import { TitleCard, type TitleCardProps } from "./components/TitleCard";
import { FactHighlight, type FactHighlightProps } from "./components/FactHighlight";
import { ImageScene } from "./components/ImageScene";
import { SubscribeCTA, type SubscribeCTAProps } from "./components/SubscribeCTA";
import { InfoCard, type InfoCardProps } from "./components/InfoCard";
import { InfoSlide, type InfoSlideProps } from "./components/InfoSlide";
import { TextOnlySlide } from "./components/TextOnlySlide";
import { TitleBanner, type TitleBannerProps } from "./components/TitleBanner";
import { NarrationSubtitle, type NarrationSubtitleProps } from "./components/NarrationSubtitle";
import { StarfieldBackground } from "./components/StarfieldBackground";
import { AnimatedBarChart, type AnimatedBarChartProps } from "./components/AnimatedBarChart";
import { DonutGauge, type DonutGaugeProps } from "./components/DonutGauge";
import { ComparisonBars, type ComparisonBarsProps } from "./components/ComparisonBars";
import {
  SectionComposition,
  type SectionCompositionProps,
} from "./components/SectionComposition";
import {
  FullVideoPreview,
  type WorkspacePreviewProps,
} from "./components/FullVideoPreview";
import {
  PREVIEW_RUNS,
  type PreviewRunManifest,
} from "./generated/previewManifestVersion";
import { theme } from "./design/theme";
import {
  accentColorTarget,
  type ColorTargetDescriptor,
  withStudioAccentPreview,
} from "./design/studioAccentPreview";
import type { TextOnlySlideProps } from "./lib/types";

const sampleData = {
  values: [
    { date: "2020-01", value: 21.4 },
    { date: "2020-04", value: -31.2 },
    { date: "2020-07", value: 33.8 },
    { date: "2020-10", value: 4.5 },
    { date: "2021-01", value: 6.3 },
    { date: "2021-04", value: 6.7 },
    { date: "2021-07", value: 2.3 },
    { date: "2021-10", value: 6.9 },
  ],
};

const DEFAULT_HIGHLIGHT_COLOR = "#FFD600";

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

function hasHighlightedKeywords(keywords?: string[]): boolean {
  return Boolean(keywords && keywords.length > 0);
}

const accentLineChartTargets: readonly ColorTargetDescriptor<LineChartProps>[] = [
  accentColorTarget<LineChartProps>(theme.accent.blue),
];

const titleCardTargets: readonly ColorTargetDescriptor<TitleCardProps>[] = [
  accentColorTarget<TitleCardProps>(theme.accent.blue),
];

const factHighlightTargets: readonly ColorTargetDescriptor<FactHighlightProps>[] = [
  accentColorTarget<FactHighlightProps>(theme.accent.blue),
];

const subscribeCtaTargets: readonly ColorTargetDescriptor<SubscribeCTAProps>[] = [
  accentColorTarget<SubscribeCTAProps>("#FF4444"),
];

const titleBannerTargets: readonly ColorTargetDescriptor<TitleBannerProps>[] = [
  accentColorTarget<TitleBannerProps>(theme.accent.blue),
];

const animatedBarChartTargets: readonly ColorTargetDescriptor<AnimatedBarChartProps>[] = [
  accentColorTarget<AnimatedBarChartProps>(theme.accent.blue),
];

const donutGaugeTargets: readonly ColorTargetDescriptor<DonutGaugeProps>[] = [
  accentColorTarget<DonutGaugeProps>(theme.accent.blue),
];

const comparisonBarsTargets: readonly ColorTargetDescriptor<ComparisonBarsProps>[] = [
  accentColorTarget<ComparisonBarsProps>(theme.accent.blue),
];

const infoCardTargets: readonly ColorTargetDescriptor<InfoCardProps>[] = [
  accentColorTarget<InfoCardProps>(theme.accent.blue),
  {
    id: "background_color",
    label: "Background",
    get: (props) => props.background_color ?? darken(props.accent_color ?? theme.accent.blue, 0.7),
    set: (props, color) => ({ ...props, background_color: color }),
  },
  {
    id: "text_box_color",
    label: "Text Box",
    get: (props) => props.text_box_color ?? lighten(props.accent_color ?? theme.accent.blue, 0.15),
    set: (props, color) => ({ ...props, text_box_color: color }),
  },
  {
    id: "frame_border_color",
    label: "Frame Border",
    get: (props) =>
      props.illustration_style === "framed"
        ? props.frame_border_color ?? lighten(props.accent_color ?? theme.accent.blue, 0.3)
        : null,
    set: (props, color) => ({ ...props, frame_border_color: color }),
    isVisible: (props) => props.illustration_style === "framed",
  },
  {
    id: "highlight_color",
    label: "Highlight",
    get: (props) =>
      hasHighlightedKeywords(props.highlighted_keywords)
        ? props.highlight_color ?? DEFAULT_HIGHLIGHT_COLOR
        : null,
    set: (props, color) => ({ ...props, highlight_color: color }),
    isVisible: (props) => hasHighlightedKeywords(props.highlighted_keywords),
  },
];

const infoSlideTargets: readonly ColorTargetDescriptor<InfoSlideProps>[] = [
  accentColorTarget<InfoSlideProps>("#2E86DE"),
  {
    id: "background_color",
    label: "Background",
    get: (props) => props.background_color ?? "#FFFFFF",
    set: (props, color) => ({ ...props, background_color: color }),
  },
  {
    id: "background_tint_color",
    label: "Backdrop Tint",
    get: (props) =>
      props.background_tint_color ?? lighten(props.accent_color ?? "#2E86DE", 0.95),
    set: (props, color) => ({ ...props, background_tint_color: color }),
  },
  {
    id: "title_color",
    label: "Title",
    get: (props) => props.title_color ?? "#0F1A30",
    set: (props, color) => ({ ...props, title_color: color }),
  },
  {
    id: "body_color",
    label: "Body",
    get: (props) => props.body_color ?? "#1E2D45",
    set: (props, color) => ({ ...props, body_color: color }),
  },
  {
    id: "highlight_color",
    label: "Highlight",
    get: (props) =>
      hasHighlightedKeywords(props.highlighted_keywords)
        ? props.highlight_color ?? darken(props.accent_color ?? "#2E86DE", 0.15)
        : null,
    set: (props, color) => ({ ...props, highlight_color: color }),
    isVisible: (props) => hasHighlightedKeywords(props.highlighted_keywords),
  },
];

const narrationSubtitleTargets: readonly ColorTargetDescriptor<NarrationSubtitleProps>[] = [
  {
    id: "highlight_color",
    label: "Highlight",
    get: (props) =>
      hasHighlightedKeywords(props.highlighted_keywords)
        ? props.highlight_color ?? DEFAULT_HIGHLIGHT_COLOR
        : null,
    set: (props, color) => ({ ...props, highlight_color: color }),
    isVisible: (props) => hasHighlightedKeywords(props.highlighted_keywords),
  },
];

const sectionCompositionTargets: readonly ColorTargetDescriptor<SectionCompositionProps>[] = [
  {
    id: "subtitle_highlight_color",
    label: "Subtitle Highlight",
    get: (props) =>
      props.narrationSubtitle && hasHighlightedKeywords(props.narrationSubtitle.highlighted_keywords)
        ? props.narrationSubtitle.highlight_color ?? DEFAULT_HIGHLIGHT_COLOR
        : null,
    set: (props, color) =>
      props.narrationSubtitle
        ? {
            ...props,
            narrationSubtitle: {
              ...props.narrationSubtitle,
              highlight_color: color,
            },
          }
        : props,
    isVisible: (props) =>
      Boolean(
        props.narrationSubtitle &&
          hasHighlightedKeywords(props.narrationSubtitle.highlighted_keywords),
      ),
  },
];

const PreviewAnimatedLineChart = withStudioAccentPreview(
  AnimatedLineChart,
  accentLineChartTargets,
);
const PreviewTitleCard = withStudioAccentPreview(TitleCard, titleCardTargets);
const PreviewFactHighlight = withStudioAccentPreview(
  FactHighlight,
  factHighlightTargets,
);
const PreviewNarrationSubtitle = withStudioAccentPreview(
  NarrationSubtitle,
  narrationSubtitleTargets,
);
const PreviewSubscribeCTA = withStudioAccentPreview(
  SubscribeCTA,
  subscribeCtaTargets,
);
const PreviewInfoCard = withStudioAccentPreview(InfoCard, infoCardTargets);
const PreviewInfoSlide = withStudioAccentPreview(InfoSlide, infoSlideTargets);
const PreviewTextOnlySlide = withStudioAccentPreview(
  TextOnlySlide,
  infoSlideTargets as readonly ColorTargetDescriptor<TextOnlySlideProps>[],
);
const PreviewTitleBanner = withStudioAccentPreview(TitleBanner, titleBannerTargets);
const PreviewAnimatedBarChart = withStudioAccentPreview(
  AnimatedBarChart,
  animatedBarChartTargets,
);
const PreviewDonutGauge = withStudioAccentPreview(DonutGauge, donutGaugeTargets);
const PreviewComparisonBars = withStudioAccentPreview(
  ComparisonBars,
  comparisonBarsTargets,
);
const PreviewSectionComposition = withStudioAccentPreview(
  SectionComposition,
  sectionCompositionTargets,
);

const sampleWorkspacePreviewProps = {
  title: "Preview Workspace Sample",
  width: 1920,
  height: 1080,
  fps: 30,
  total_frames: 300,
  static_root: "_preview/sample",
  sections: [
    {
      section_id: 1,
      duration_frames: 300,
      transition_to_next: null,
      props: {
        slots: [
          {
            type: "image",
            imagePath: "sample.jpg",
            durationFrames: 300,
            preset: "parallax",
            direction: "left",
          },
        ],
        transition: {
          type: "fade",
          durationFrames: 9,
        },
        narrationSubtitle: {
          word_timestamps: [
            { word: "Preview", start: 0, end: 0.4 },
            { word: "mode", start: 0.4, end: 0.8 },
            { word: "loads", start: 0.8, end: 1.2 },
            { word: "full", start: 1.2, end: 1.5 },
            { word: "workspace", start: 1.5, end: 2.1 },
            { word: "props.", start: 2.1, end: 2.5 },
          ],
        },
      },
    },
  ],
  audio: {
    background_music_volume: 0.15,
    transition_sfx_volume: 0.15,
  },
} satisfies WorkspacePreviewProps;

type PreviewRunCompositionProps = WorkspacePreviewProps & PreviewRunManifest;

const previewRunDefaultProps = (
  run: PreviewRunManifest,
): PreviewRunCompositionProps => ({
  ...sampleWorkspacePreviewProps,
  ...run,
  title: run.compositionId,
});

const calculateFullVideoPreviewMetadata: CalculateMetadataFunction<
  PreviewRunCompositionProps
> = async ({ props, abortSignal }) => {
  const manifestUrl = `${staticFile(props.manifestPath)}?v=${props.manifestVersion}`;
  const response = await fetch(manifestUrl, {
    signal: abortSignal,
    cache: "no-store",
  });

  if (!response.ok) {
    return {
      props,
      durationInFrames: props.total_frames,
      width: props.width,
      height: props.height,
      fps: props.fps,
    };
  }

  const manifest = (await response.json()) as WorkspacePreviewProps;
  const runProps = {
    ...manifest,
    compositionId: props.compositionId,
    manifestPath: props.manifestPath,
    manifestVersion: props.manifestVersion,
  } satisfies PreviewRunCompositionProps;
  return {
    props: runProps,
    durationInFrames: manifest.total_frames,
    width: manifest.width,
    height: manifest.height,
    fps: manifest.fps,
  };
};

export const Root: React.FC = () => {
  return (
    <>
      <Folder name="PreviewRuns">
        {PREVIEW_RUNS.map((run) => (
          <Composition
            key={run.compositionId}
            id={run.compositionId}
            component={FullVideoPreview as unknown as ComponentType<PreviewRunCompositionProps>}
            durationInFrames={sampleWorkspacePreviewProps.total_frames}
            fps={sampleWorkspacePreviewProps.fps}
            width={sampleWorkspacePreviewProps.width}
            height={sampleWorkspacePreviewProps.height}
            defaultProps={previewRunDefaultProps(run)}
            calculateMetadata={calculateFullVideoPreviewMetadata}
          />
        ))}
      </Folder>
      <Composition
        id="AnimatedLineChart"
        component={PreviewAnimatedLineChart as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          data: sampleData,
          title: "U.S. GDP Growth",
          subtitle: "Quarterly % change, annualized",
          y_axis_label: "% Change",
          accent_color: "#00D4FF",
          animation_duration_frames: 90,
        }}
      />
      <Composition
        id="TitleCard"
        component={PreviewTitleCard as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "La Era Dorada",
          accent_color: "#00D4FF",
        }}
      />
      <Composition
        id="FactHighlight"
        component={PreviewFactHighlight as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          value: "28",
          label: "marcas que desaparecieron",
          unit: "",
          accent_color: "#FF4444",
        }}
      />
      <Composition
        id="ImageScene"
        component={ImageScene as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          image_path: "sample.jpg",
          animation_preset: "parallax",
          direction: "left",
        }}
      />
      <Composition
        id="NarrationSubtitle"
        component={PreviewNarrationSubtitle as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          word_timestamps: [
            { word: "Planning", start: 0.1, end: 0.4 },
            { word: "before", start: 0.4, end: 0.6 },
            { word: "work", start: 0.6, end: 0.9 },
            { word: "can", start: 0.9, end: 1.1 },
            { word: "significantly", start: 1.1, end: 1.7 },
            { word: "improve", start: 1.7, end: 2.1 },
            { word: "your", start: 2.1, end: 2.3 },
            { word: "focus.", start: 2.3, end: 2.8 },
            { word: "Teams", start: 3.0, end: 3.4 },
            { word: "show", start: 3.4, end: 3.6 },
            { word: "that", start: 3.6, end: 3.8 },
            { word: "even", start: 3.8, end: 4.0 },
            { word: "fifteen", start: 4.0, end: 4.4 },
            { word: "minutes", start: 4.4, end: 4.8 },
            { word: "makes", start: 4.9, end: 5.2 },
            { word: "a", start: 5.2, end: 5.3 },
            { word: "difference.", start: 5.3, end: 5.9 },
            { word: "Your", start: 6.2, end: 6.4 },
            { word: "plan", start: 6.4, end: 6.7 },
            { word: "gets", start: 6.7, end: 6.9 },
            { word: "clearer,", start: 6.9, end: 7.3 },
            { word: "your", start: 7.4, end: 7.6 },
            { word: "handoff", start: 7.6, end: 7.9 },
            { word: "improves,", start: 7.9, end: 8.4 },
            { word: "and", start: 8.5, end: 8.6 },
            { word: "your", start: 8.6, end: 8.8 },
            { word: "review", start: 8.8, end: 9.1 },
            { word: "quality", start: 9.1, end: 9.5 },
            { word: "increases.", start: 9.5, end: 9.9 },
          ],
          highlighted_keywords: ["focus", "fifteen", "plan", "review"],
        }}
      />
      <Composition
        id="StarfieldBackground"
        component={StarfieldBackground as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          particle_count: 30,
          drift_speed: 1,
          seed: 42,
        }}
      />
      <Composition
        id="InfoCard"
        component={PreviewInfoCard as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          text: "A short planning pass can reduce rework by clarifying the next decision before production starts.",
          accent_color: "#4CAF50",
          layout: "image-left",
          show_particles: true,
          highlighted_keywords: ["planning", "rework", "decision"],
        }}
      />
      <Composition
        id="InfoCard-Right"
        component={PreviewInfoCard as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          text: "A simple checklist keeps handoffs consistent by making each required artifact visible before review.",
          accent_color: "#2196F3",
          layout: "image-right",
          show_particles: true,
          illustration_style: "framed",
          highlighted_keywords: ["checklist", "handoffs", "review"],
        }}
      />
      <Composition
        id="InfoSlide"
        component={PreviewInfoSlide as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "Workflow Review Benefits",
          text: "A short review step can improve output quality:\n- Catches missing artifacts early\n- Clarifies the next action\n- Reduces repeated work\n- Keeps decisions visible",
          accent_color: "#2E86DE",
          illustration_url: "sample.jpg",
          layout: "image-right",
          highlighted_keywords: ["review", "quality", "decisions"],
        }}
      />
      <Composition
        id="InfoSlide-Left"
        component={PreviewInfoSlide as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "Checklist Research",
          text: "Teams use checklists to make repeated work easier to verify.\nConsistent artifacts paired with clear review criteria produce better handoffs.",
          accent_color: "#4CAF50",
          illustration_url: "sample.jpg",
          layout: "image-left",
          highlighted_keywords: ["checklists", "review", "handoffs"],
        }}
      />
      <Composition
        id="TextOnlySlide"
        component={PreviewTextOnlySlide as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "How To Review It",
          text: "- Confirm the required files exist\n- Check the main output first\n- Compare against the intended brief\n- Stop when a blocking issue appears",
          accent_color: "#2E86DE",
          highlighted_keywords: ["files", "brief", "stop"],
        }}
      />
      <Composition
        id="TitleBanner"
        component={PreviewTitleBanner as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "Step 3: Review the Final Package",
          section_number: 3,
          accent_color: "#2196F3",
        }}
      />
      <Composition
        id="SubscribeCTA"
        component={PreviewSubscribeCTA as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={120}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          cta_text: "SUBSCRIBE",
          accent_color: "#FF4444",
        }}
      />
      <Composition
        id="AnimatedBarChart"
        component={PreviewAnimatedBarChart as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "Top Workflow Improvements",
          subtitle: "Effectiveness score (out of 100)",
          bars: [
            { label: "Checklist", value: 92 },
            { label: "Preview", value: 88 },
            { label: "Tracing", value: 85 },
            { label: "Retries", value: 78 },
            { label: "Reports", value: 72 },
          ],
          accent_color: "#4CAF50",
          value_suffix: "",
        }}
      />
      <Composition
        id="DonutGauge"
        component={PreviewDonutGauge as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          value: 67,
          unit: "%",
          accent_color: "#FF9800",
        }}
      />
      <Composition
        id="ComparisonBars"
        component={PreviewComparisonBars as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "Time Saved per Review",
          items: [
            { label: "Script", value: 255 },
            { label: "Visuals", value: 150 },
            { label: "Audio", value: 210 },
            { label: "Final QA", value: 120 },
          ],
          accent_color: "#2196F3",
          value_suffix: " min",
        }}
      />
      <Composition
        id="SectionComposition"
        component={PreviewSectionComposition as unknown as ComponentType<Record<string, unknown>>}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          slots: [
            {
              type: "image",
              imagePath: "sample.jpg",
              durationFrames: 150,
              preset: "parallax",
              direction: "left",
            },
            {
              type: "image",
              imagePath: "sample.jpg",
              durationFrames: 150,
              preset: "drift",
              direction: "right",
            },
          ],
          transition: { type: "fade", durationFrames: 9 },
        }}
      />
    </>
  );
};
