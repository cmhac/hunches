import { ReactNode, CSSProperties } from 'react';
/**
 * Textual DataTable: header row, row cursor, cells padded 1 cell each side.
 * @startingPoint section="Data" subtitle="Row-cursor table" viewport="700x260"
 */
export interface DataTableColumn {
  label: ReactNode;
  /** CSS grid track: "8ch", "1fr", "minmax(0,2fr)" */
  width?: string;
  align?: 'left' | 'right' | 'center';
}
export interface DataTableRow {
  cells: ReactNode[];
  key?: string;
  dim?: boolean;
  strong?: boolean;
}
export interface DataTableProps {
  columns: DataTableColumn[];
  rows: (ReactNode[] | DataTableRow)[];
  /** Highlighted row index (-1 none) */
  cursor?: number;
  /** Cursor colour: blue when focused, ink when blurred */
  focused?: boolean;
  header?: boolean;
  zebra?: boolean;
  onRowClick?: (index: number) => void;
  style?: CSSProperties;
}
export declare function DataTable(props: DataTableProps): JSX.Element;
