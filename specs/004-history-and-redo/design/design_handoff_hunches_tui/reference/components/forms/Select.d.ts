/** Dropdown (Textual Select), same 3-row footprint as Input. */
export interface SelectOption { label: string; value: string; }
export interface SelectProps {
  value?: string;
  options?: (SelectOption | string)[];
  open?: boolean;
  focused?: boolean;
  /** 1-row variant without border */
  compact?: boolean;
  onPick?: (v: string) => void;
}
export declare function Select(props: SelectProps): JSX.Element;
