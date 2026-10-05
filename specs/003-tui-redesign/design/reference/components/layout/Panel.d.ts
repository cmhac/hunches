import { ReactNode, CSSProperties } from 'react';
/** Bordered region (Textual `border: round`). Border sits in a 1-cell gutter; title on the top edge, subtitle bottom-right. */
export interface PanelProps {
  /** Usually the file or thing shown: "seeds.csv · 14" */
  title?: ReactNode;
  /** Bottom-right hint, e.g. "3 of 12" */
  subtitle?: ReactNode;
  /** Focus: blue border + blue title. Exactly one panel per screen is focused. */
  focused?: boolean;
  /** Horizontal padding in cells (default 1) */
  pad?: number;
  /** flex-grow inside a row/column; true = 1 */
  grow?: boolean | number;
  /** Background behind the title cut-out; match the parent */
  bg?: string;
  children?: ReactNode;
  style?: CSSProperties;
  innerStyle?: CSSProperties;
}
export declare function Panel(props: PanelProps): JSX.Element;
