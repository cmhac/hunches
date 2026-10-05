/** Horizontal bar in block glyphs with 1/8-cell precision. Use inside tables for counts and rates. */
export interface BarProps {
  value?: number;
  max?: number;
  /** Width in cells */
  width?: number;
  color?: string;
  /** Draw the ─ track for the unused part (default true) */
  track?: boolean;
}
export declare function Bar(props: BarProps): JSX.Element;
