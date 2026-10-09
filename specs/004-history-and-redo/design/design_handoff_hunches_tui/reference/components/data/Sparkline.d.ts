/** One-row trend in ▁▂▃▄▅▆▇█, e.g. target metric per prompt version. */
export interface SparklineProps {
  values: number[];
  min?: number;
  max?: number;
  color?: string;
}
export declare function Sparkline(props: SparklineProps): JSX.Element;
