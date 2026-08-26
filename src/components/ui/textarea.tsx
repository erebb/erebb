import * as React from 'react';
import { cn } from '@/lib/utils';

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'flex min-h-[120px] w-full rounded-xl border-2 border-duo-gray-100 bg-duo-gray-50 px-4 py-3 text-sm font-semibold text-duo-gray-700 placeholder:text-duo-gray-300 focus:border-duo-blue focus:bg-white focus:outline-none disabled:opacity-50',
      className
    )}
    {...props}
  />
));
Textarea.displayName = 'Textarea';

export { Textarea };
