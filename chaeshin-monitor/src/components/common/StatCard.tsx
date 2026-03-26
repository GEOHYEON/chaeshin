"use client";

import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  variant?: "default" | "success" | "warning" | "error";
  className?: string;
}

const variants = {
  default: {
    card: "border-[hsl(var(--border))]",
    iconBg: "bg-[hsl(var(--muted))]",
  },
  success: {
    card: "border-green-200",
    iconBg: "bg-green-50",
  },
  warning: {
    card: "border-amber-200",
    iconBg: "bg-amber-50",
  },
  error: {
    card: "border-red-200",
    iconBg: "bg-red-50",
  },
};

export function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  variant = "default",
  className,
}: StatCardProps) {
  const v = variants[variant];

  return (
    <div
      className={cn(
        "rounded-xl border bg-white p-5 shadow-sm hover:shadow-md transition-all duration-200",
        v.card,
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
            {title}
          </p>
          <p className="text-2xl font-bold tracking-tight">{value}</p>
          {description && (
            <p className="text-[11px] text-[hsl(var(--muted-foreground))]">{description}</p>
          )}
        </div>
        {icon && (
          <div className={cn("flex items-center justify-center w-10 h-10 rounded-lg", v.iconBg)}>
            {icon}
          </div>
        )}
      </div>
      {trend && (
        <div className="mt-3 flex items-center gap-1.5">
          <span
            className={cn(
              "text-xs font-semibold",
              trend.isPositive ? "text-green-600" : "text-red-500"
            )}
          >
            {trend.isPositive ? "+" : ""}{trend.value}%
          </span>
          <span className="text-[11px] text-[hsl(var(--muted-foreground))]">vs 지난 주</span>
        </div>
      )}
    </div>
  );
}
