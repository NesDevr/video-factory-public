import React from "react";
import type { ComponentType } from "react";
import { AbsoluteFill } from "remotion";
import { FactHighlight } from "./FactHighlight";
import { ImageScene } from "./ImageScene";
import { SubscribeCTA } from "./SubscribeCTA";
import { TitleBanner } from "./TitleBanner";
import { TitleCard } from "./TitleCard";

const FIGURE_COMPONENTS: Record<string, ComponentType<any>> = {
  FactHighlight,
  SubscribeCTA,
  TitleBanner,
  TitleCard,
};

export interface BackdropFigureSceneProps {
  background_path: string;
  animation_preset?: string;
  direction?: string;
  figure_component: string;
  figure_props: Record<string, unknown>;
}

export const BackdropFigureScene: React.FC<BackdropFigureSceneProps> = ({
  background_path,
  animation_preset = "parallax",
  direction = "left",
  figure_component,
  figure_props,
}) => {
  const Figure = FIGURE_COMPONENTS[figure_component];
  if (!Figure) {
    throw new Error(`Unknown backdrop figure component: ${figure_component}`);
  }

  return (
    <AbsoluteFill>
      <ImageScene
        image_path={background_path}
        animation_preset={animation_preset}
        direction={direction}
      />
      <Figure {...figure_props} />
    </AbsoluteFill>
  );
};
