import { ReactNode } from 'react';
/** Centered dialog over a dimmed screen (Textual ModalScreen). Must be inside a Terminal. */
export interface ModalProps {
  title?: ReactNode;
  /** Width in cells (default 60) */
  width?: number;
  /** Fixed height in rows (default: fit content) */
  height?: number;
  /** No gaps or vertical padding; for full-screen editors like the prompt proposal */
  dense?: boolean;
  children?: ReactNode;
  /** Right-aligned buttons, primary action last */
  actions?: ReactNode;
}
export declare function Modal(props: ModalProps): JSX.Element;
