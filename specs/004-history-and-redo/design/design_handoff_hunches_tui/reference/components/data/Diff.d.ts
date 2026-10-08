/** Unified diff with +/- line tinting. Used for prompt edit proposals. */
export interface DiffProps {
  /** difflib.unified_diff output joined with \n */
  text: string;
}
export declare function Diff(props: DiffProps): JSX.Element;
