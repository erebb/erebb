import * as React from 'react';
import { cn } from '@/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'flex h-12 w-full rounded-xl border border-duo-gray-100 bg-surface px-4 text-base text-duo-gray-700 placeholder:text-duo-gray-300 focus:border-duo-blue focus:outline-none focus:ring-2 focus:ring-duo-blue/20 disabled:opacity-50',
        className
      )}
      {...props}
    />
  )
);
Input.displayName = 'Input';

export { Input };
