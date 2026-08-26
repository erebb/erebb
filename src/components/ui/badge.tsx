import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-extrabold',
  {
    variants: {
      variant: {
        green: 'bg-duo-green-light text-duo-green-dark',
        blue: 'bg-duo-blue-light text-duo-blue-dark',
        gold: 'bg-duo-gold-light text-duo-gold-dark',
        red: 'bg-duo-red-light text-duo-red-dark',
        gray: 'bg-duo-gray-100 text-duo-gray-500',
      },
    },
    defaultVariants: { variant: 'gray' },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
