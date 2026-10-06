/** One-row key bar (Textual Footer). Lists the bindings of the focused screen, most important first. */
export interface FooterKey {
  /** Key as displayed: "a", "F2", "↑↓", "0-9", "enter" */
  key: string;
  label: string;
  disabled?: boolean;
  onClick?: () => void;
}
export interface FooterProps {
  keys?: FooterKey[];
  /** Right-aligned slot; defaults to "^p palette" */
  right?: React.ReactNode;
}
export declare function Footer(props: FooterProps): JSX.Element;
