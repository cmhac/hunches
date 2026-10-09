/** Taxonomy label as ■ name. Colour from --label-N by taxonomy.yaml order; off_topic always grey. */
export interface LabelTagProps {
  name: string;
  /** var(--label-1) … var(--label-8) */
  color?: string;
  dim?: boolean;
}
export declare function LabelTag(props: LabelTagProps): JSX.Element;
