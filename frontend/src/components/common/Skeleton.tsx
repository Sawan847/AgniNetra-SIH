import React from "react";

export function Skeleton({
  width = "100%",
  height = "20px",
  borderRadius = "6px",
  style = {},
}: {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className="skeleton"
      style={{
        width,
        height,
        borderRadius,
        ...style,
      }}
    />
  );
}

export function CardSkeleton({ height = "180px" }: { height?: string }) {
  return (
    <div className="card" style={{ height }}>
      <Skeleton width="40%" height="22px" style={{ marginBottom: 14 }} />
      <Skeleton width="90%" height="16px" style={{ marginBottom: 10 }} />
      <Skeleton width="75%" height="16px" style={{ marginBottom: 10 }} />
      <Skeleton width="55%" height="16px" />
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="table-container">
      <table className="table">
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i}>
                <Skeleton width="70%" height="14px" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c}>
                  <Skeleton width={`${50 + (c * 10) % 40}%`} height="14px" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
