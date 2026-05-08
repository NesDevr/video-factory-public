import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
} from "remotion";
import {
  SectionComposition,
  type SectionCompositionProps,
} from "./SectionComposition";

export type WorkspacePreviewTransition = {
  type: string;
  duration_frames: number;
};

export type WorkspacePreviewSection = {
  section_id: number;
  duration_frames: number;
  transition_to_next?: WorkspacePreviewTransition | null;
  props: SectionCompositionProps;
};

export type WorkspacePreviewAudio = {
  narration_path?: string | null;
  background_music_path?: string | null;
  transition_sfx_path?: string | null;
  background_music_volume: number;
  transition_sfx_volume: number;
};

export type WorkspacePreviewProps = {
  title: string;
  width: number;
  height: number;
  fps: number;
  total_frames: number;
  static_root: string;
  sections: WorkspacePreviewSection[];
  audio: WorkspacePreviewAudio;
};

const computeSectionStartFrames = (
  sections: WorkspacePreviewSection[],
): number[] => {
  const starts: number[] = [];
  let cursor = 0;

  for (const section of sections) {
    starts.push(cursor);
    cursor += section.duration_frames - (section.transition_to_next?.duration_frames ?? 0);
  }

  return starts;
};

export const FullVideoPreview: React.FC<WorkspacePreviewProps> = ({
  sections,
  audio,
}) => {
  if (sections.length === 0) {
    throw new Error("FullVideoPreview requires at least one section");
  }

  const startFrames = computeSectionStartFrames(sections);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {audio.narration_path ? <Audio src={staticFile(audio.narration_path)} /> : null}
      {audio.background_music_path ? (
        <Audio
          src={staticFile(audio.background_music_path)}
          volume={audio.background_music_volume}
        />
      ) : null}
      {audio.transition_sfx_path ? (
        <Audio
          src={staticFile(audio.transition_sfx_path)}
          volume={audio.transition_sfx_volume}
        />
      ) : null}

      {sections.map((section, index) => (
        <Sequence
          key={section.section_id}
          from={startFrames[index]}
          durationInFrames={section.duration_frames}
          premountFor={30}
        >
          <SectionComposition {...section.props} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
