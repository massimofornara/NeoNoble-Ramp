declare module '@/components/ui/button' {
  import * as React from 'react';
  export const Button: React.ForwardRefExoticComponent<any>;
  export const buttonVariants: (...args: any[]) => string;
}

declare module '@/components/ui/dialog' {
  import * as React from 'react';
  export const Dialog: React.ComponentType<any>;
  export const DialogPortal: React.ComponentType<any>;
  export const DialogOverlay: React.ForwardRefExoticComponent<any>;
  export const DialogTrigger: React.ComponentType<any>;
  export const DialogClose: React.ComponentType<any>;
  export const DialogContent: React.ForwardRefExoticComponent<any>;
  export const DialogHeader: React.ComponentType<any>;
  export const DialogFooter: React.ComponentType<any>;
  export const DialogTitle: React.ForwardRefExoticComponent<any>;
  export const DialogDescription: React.ForwardRefExoticComponent<any>;
}

declare module '@/hooks/use-toast' {
  export function toast(input: {
    title?: string;
    description?: string;
    variant?: 'default' | 'destructive';
    [key: string]: unknown;
  }): { id: string; dismiss: () => void; update: (props: any) => void };
  export function useToast(): any;
}
