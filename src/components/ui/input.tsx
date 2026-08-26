import * as React from 'react';
import { cn } from '@/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'flex h-12 w-full rounded-xl border-2 border-duo-gray-100 bg-duo-gray-50 px-4 text-base font-semibold text-duo-gray-700 placeholder:text-duo-gray-300 focus:border-duo-blue focus:bg-white focus:outline-none disabled:opacity-50',
        className
      )}
      {...props}
    />
  )
);
Input.displayName = 'Input';

export { Input };
