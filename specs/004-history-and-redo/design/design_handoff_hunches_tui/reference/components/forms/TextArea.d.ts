/** Multi-line editor (Textual TextArea) with line numbers and light yaml/markdown highlighting. */
export interface TextAreaProps {
  /** File name: "taxonomy.yaml (editable)" */
  title?: string;
  text?: string;
  language?: 'yaml' | 'markdown';
  focused?: boolean;
  lineNumbers?: boolean;
  /** 0-based line with the cursor */
  cursorLine?: number;
  grow?: boolean | number;
}
export declare function TextArea(props: TextAreaProps): JSX.Element;
