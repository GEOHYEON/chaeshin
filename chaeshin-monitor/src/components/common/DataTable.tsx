"use client";

import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface Column<T> {
  key: keyof T | string;
  header: string;
  render?: (item: T, index: number) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (item: T, index: number) => void;
  selectedIndex?: number;
  emptyMessage?: string;
  className?: string;
}

/**
 * Toss 스타일 데이터 테이블
 * - 깔끔한 행 구분
 * - 호버 효과
 * - 선택 상태 표시
 */
export function DataTable<T extends object>({
  columns,
  data,
  onRowClick,
  selectedIndex,
  emptyMessage = "데이터가 없습니다",
  className,
}: DataTableProps<T>) {
  return (
    <div className={cn("rounded-xl border border-border overflow-hidden", className)}>
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50 hover:bg-muted/50">
            {columns.map((column) => (
              <TableHead
                key={String(column.key)}
                className={cn(
                  "text-xs font-medium text-muted-foreground uppercase tracking-wide",
                  column.className
                )}
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="h-32 text-center text-muted-foreground"
              >
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            data.map((item, index) => (
              <TableRow
                key={index}
                onClick={() => onRowClick?.(item, index)}
                className={cn(
                  "transition-colors",
                  onRowClick && "cursor-pointer",
                  selectedIndex === index && "bg-primary/10"
                )}
              >
                {columns.map((column) => (
                  <TableCell key={String(column.key)} className={column.className}>
                    {column.render
                      ? column.render(item, index)
                      : String(item[column.key as keyof T] ?? "")}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * 상태 뱃지 컴포넌트
 */
export function StatusBadge({
  status,
  children,
}: {
  status: "success" | "error" | "pending" | "default";
  children: React.ReactNode;
}) {
  const variants = {
    success: "bg-green-50 text-green-700 border-green-200",
    error: "bg-red-50 text-red-700 border-red-200",
    pending: "bg-yellow-50 text-yellow-700 border-yellow-200",
    default: "bg-gray-50 text-gray-600 border-gray-200",
  };

  return (
    <Badge variant="outline" className={cn("font-medium", variants[status])}>
      {children}
    </Badge>
  );
}
