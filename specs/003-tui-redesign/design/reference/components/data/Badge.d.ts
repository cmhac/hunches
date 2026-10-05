import { ReactNode } from 'react';
/** Reverse-video status word: PASS, FAIL, STALE, DIFFERS. One cell padding each side. */
export interface BadgeProps {
  tone?: 'pass' | 'fail' | 'stale' | 'info' | 'neutral' | 'primary';
  /** Uppercase single word */
  children?: ReactNode;
}
export declare function Badge(props: BadgeProps): JSX.Element;
