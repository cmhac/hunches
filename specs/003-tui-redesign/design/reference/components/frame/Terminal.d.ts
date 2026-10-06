import { ReactNode, CSSProperties } from 'react';
/**
 * Terminal viewport sized in cells. Every hunches screen renders inside one.
 * @startingPoint section="Frame" subtitle="80×24 terminal with header and footer" viewport="760x560"
 */
export interface TerminalProps {
  /** Columns (default 80, the smallest supported) */
  cols?: number;
  /** Rows (default 24) */
  rows?: number;
  /** Window title shown in the chrome */
  title?: string;
  /** Draw window chrome around the cell grid (default true) */
  chrome?: boolean;
  children?: ReactNode;
  style?: CSSProperties;
}
export declare function Terminal(props: TerminalProps): JSX.Element;
