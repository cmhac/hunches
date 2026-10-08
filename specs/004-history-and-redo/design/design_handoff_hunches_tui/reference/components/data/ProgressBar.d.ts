/** Textual-style ━ progress bar with percentage and optional ETA. */
export interface ProgressBarProps {
  value?: number;
  total?: number;
  /** Bar width in cells */
  width?: number;
  /** "0:12:40" */
  eta?: string;
  color?: string;
}
export declare function ProgressBar(props: ProgressBarProps): JSX.Element;
