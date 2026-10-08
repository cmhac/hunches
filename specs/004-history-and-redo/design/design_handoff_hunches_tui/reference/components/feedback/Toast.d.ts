/** Transient notification (Textual app.notify), bottom-right above the footer. */
export interface ToastProps {
  title?: string;
  message: string;
  severity?: 'information' | 'warning' | 'error' | 'success';
  /** Position absolutely inside the Terminal (default true) */
  floating?: boolean;
}
export declare function Toast(props: ToastProps): JSX.Element;
