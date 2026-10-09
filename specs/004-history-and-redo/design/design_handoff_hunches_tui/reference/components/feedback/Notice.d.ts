import { ReactNode } from 'react';
/** One-line status message under a panel, or a full-width banner. Text starts with a word that carries the meaning. */
export interface NoticeProps {
  tone?: 'note' | 'ok' | 'warn' | 'error' | 'stale';
  /** Tinted full-width bar, bold */
  banner?: boolean;
  children?: ReactNode;
}
export declare function Notice(props: NoticeProps): JSX.Element;
