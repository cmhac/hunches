/** One labelling choice: key cap, mark, label name, description. ● / ○ in single mode, ■ / □ in multi. */
export interface LabelOptionProps {
  /** Key: "1".."9", "0" for off_topic */
  k: string;
  name: string;
  description?: string;
  color?: string;
  checked?: boolean;
  mode?: 'single' | 'multi';
  onClick?: () => void;
}
export declare function LabelOption(props: LabelOptionProps): JSX.Element;
