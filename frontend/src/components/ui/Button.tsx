// src/components/ui/Button.tsx
import React, { ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/utils';

export interface ButtonProps extends ButtonHTMLAttributes < HTMLButtonElement > {
  variant ? : 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
  size ? : 'sm' | 'md' | 'lg';
  isLoading ? : boolean;
}

const Button = forwardRef < HTMLButtonElement,
  ButtonProps > (
    ({ className, variant = 'primary', size = 'md', isLoading, children, ...props }, ref) => {
      
      // Base styles for all buttons
      const baseStyles = "inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none";
      
      // Variants matching our tailwind.config.ts tokens
      const variants = {
        primary: "bg-brand-500 text-white hover:bg-brand-900",
        secondary: "bg-surface-muted text-slate-800 hover:bg-slate-200",
        danger: "bg-status-danger text-white hover:bg-red-600",
        ghost: "bg-transparent hover:bg-surface-muted text-slate-700",
        outline: "border border-slate-300 bg-transparent hover:bg-slate-50 text-slate-700"
      };
      
      // Sizes for different ERP contexts (tables vs main forms)
      const sizes = {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4 py-2 text-sm",
        lg: "h-12 px-8 text-base"
      };
      
      return (
        <button
        ref={ref}
        disabled={isLoading || props.disabled}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      >
        {isLoading ? (
          <span className="mr-2 animate-spin rounded-full h-4 w-4 border-b-2 border-white"></span>
        ) : null}
        {children}
      </button>
      );
    }
  );

Button.displayName = "Button";
export { Button };