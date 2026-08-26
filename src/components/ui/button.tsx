import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-2xl font-extrabold uppercase tracking-wide transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-duo-blue disabled:pointer-events-none disabled:opacity-50 select-none',
  {
    variants: {
      variant: {
        primary:
          'bg-duo-green text-white shadow-duo-btn hover:brightness-105 active:translate-y-1 active:shadow-none',
        blue: 'bg-duo-blue text-white shadow-duo-btn-blue hover:brightness-105 active:translate-y-1 active:shadow-none',
        danger:
          'bg-duo-red text-white shadow-duo-btn-red hover:brightness-105 active:translate-y-1 active:shadow-none',
        outline:
          'bg-white text-duo-gray-700 border-2 border-duo-gray-100 shadow-duo-card hover:bg-duo-gray-50 active:translate-y-0.5 active:shadow-none',
        ghost: 'text-duo-gray-500 hover:bg-duo-gray-50 hover:text-duo-gray-700',
      },
      size: {
        default: 'h-12 px-6 text-sm',
        sm: 'h-9 px-4 text-xs rounded-xl',
        lg: 'h-14 px-8 text-base',
        icon: 'h-10 w-10 rounded-xl normal-case',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
