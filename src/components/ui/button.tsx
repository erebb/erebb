import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// Düz, sakin düğmeler: büyük harf yok (küçük harfli metin daha hızlı okunur, Türkçe İ sorunu da
// çıkmaz), 3B gölge ve zıplama yok. Tek dolgu rengi vurgu (mavi); yeşil/kırmızı yalnız geri bildirimde.
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-duo-blue focus-visible:ring-offset-2 focus-visible:ring-offset-duo-gray-50 disabled:pointer-events-none disabled:opacity-50 select-none',
  {
    variants: {
      variant: {
        primary: 'bg-duo-blue text-white hover:brightness-110 active:brightness-95',
        blue: 'bg-duo-blue-light text-duo-blue-dark hover:brightness-[0.97] active:brightness-95',
        success: 'bg-duo-green text-white hover:brightness-110 active:brightness-95',
        danger: 'bg-duo-red text-white hover:brightness-110 active:brightness-95',
        outline:
          'border border-duo-gray-100 bg-surface text-duo-gray-700 hover:border-duo-gray-300/50 hover:bg-duo-gray-50 active:bg-duo-gray-100',
        ghost: 'text-duo-gray-500 hover:bg-duo-gray-100 hover:text-duo-gray-700',
      },
      size: {
        default: 'h-11 px-5 text-sm',
        sm: 'h-9 px-3.5 text-sm rounded-lg',
        lg: 'h-12 px-6 text-base',
        icon: 'h-10 w-10 rounded-xl',
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
