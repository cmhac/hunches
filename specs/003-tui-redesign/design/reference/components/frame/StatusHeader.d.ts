/** One-row app header: wordmark, project, 9-stage stepper, stage name, running cost. Always the first row. */
export interface StatusHeaderProps {
  /** Project name (the directory containing .hunches/) */
  project?: string;
  /** Current stage 1-9; 0 = Setup */
  stage?: number;
  /** Stage names; defaults to the nine spec stages */
  stages?: string[];
  /** Total dollars so far (cost.json) */
  cost?: number;
  /** Models genai-prices can't price. Non-empty → "cost ?" warning, never $0 */
  unknownModels?: string[];
  /** Mock-only: click a stepper dot */
  onStage?: (n: number) => void;
}
export declare function StatusHeader(props: StatusHeaderProps): JSX.Element;
export declare const STAGES: string[];
