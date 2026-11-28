import * as React from 'react';
import { cn } from '@/lib/utils';

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'flex min-h-[120px] w-full rounded-xl border border-duo-gray-100 bg-surface px-4 py-3 text-sm text-duo-gray-700 placeholder:text-duo-gray-300 focus:border-duo-blue focus:outline-none focus:ring-2 focus:ring-duo-blue/20 disabled:opacity-50',
      className
    )}
    {...props}
  />
));
Textarea.displayName = 'Textarea';

export { Textarea };
