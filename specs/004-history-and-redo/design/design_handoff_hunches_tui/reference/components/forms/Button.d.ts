import { ReactNode } from 'react';
/** Textual Button: 3 rows, min 16 cells, bevelled. compact = 1 row. */
export interface ButtonProps {
  variant?: 'default' | 'primary' | 'success' | 'error';
  focused?: boolean;
  disabled?: boolean;
  compact?: boolean;
  onClick?: () => void;
  children?: ReactNode;
}
export declare function Button(props: ButtonProps): JSX.Element;
