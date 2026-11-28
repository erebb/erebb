import * as React from 'react';
import * as ProgressPrimitive from '@radix-ui/react-progress';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface ProgressProps extends React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> {
  value?: number;
  indicatorClassName?: string;
}

const Progress = React.forwardRef<React.ElementRef<typeof ProgressPrimitive.Root>, ProgressProps>(
  ({ className, value = 0, indicatorClassName, ...props }, ref) => (
    <ProgressPrimitive.Root
      ref={ref}
      className={cn('relative h-2 w-full overflow-hidden rounded-full bg-duo-gray-100', className)}
      value={value}
      {...props}
    >
      <ProgressPrimitive.Indicator asChild>
        <motion.div
          className={cn('h-full rounded-full bg-duo-blue', indicatorClassName)}
          initial={false}
          animate={{ width: `${Math.min(100, Math.max(0, value))}%` }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
        />
      </ProgressPrimitive.Indicator>
    </ProgressPrimitive.Root>
  )
);
Progress.displayName = 'Progress';

export { Progress };
