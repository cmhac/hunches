import { CSSProperties } from 'react';
/** Single-line text input, 3 rows tall (Textual Input with tall border). */
export interface InputProps {
  value?: string;
  placeholder?: string;
  focused?: boolean;
  /** 1-row variant without border (Textual compact), for dense forms like Setup */
  compact?: boolean;
  /** Pass to make it a live <input> in mocks */
  onChange?: (v: string) => void;
  onSubmit?: (v: string) => void;
  style?: CSSProperties;
}
export declare function Input(props: InputProps): JSX.Element;
