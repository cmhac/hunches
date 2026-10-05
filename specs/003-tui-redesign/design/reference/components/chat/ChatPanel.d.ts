/**
 * Agent conversation: message log + input (app.py ChatPanel). Used in stages 1 and 3.
 * @startingPoint section="Chat" subtitle="Smart-model chat panel" viewport="420x420"
 */
export interface ChatMessage {
  role: 'user' | 'agent' | 'tool' | 'error';
  text: string;
}
export interface ChatPanelProps {
  title?: string;
  /** Model string shown bottom-right of the border */
  model?: string;
  messages?: ChatMessage[];
  /** Partial reply being streamed (teal, with cursor) */
  streaming?: string;
  input?: string;
  placeholder?: string;
  focused?: boolean;
  grow?: boolean | number;
  onInput?: (v: string) => void;
  onSubmit?: (v: string) => void;
}
export declare function ChatPanel(props: ChatPanelProps): JSX.Element;
