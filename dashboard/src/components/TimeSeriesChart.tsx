"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { t: string; v: number };

export function TimeSeriesChart({
  data,
  color = "#1a5f7a",
  unit = "",
}: {
  data: Point[];
  color?: string;
  unit?: string;
}) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(26,40,48,0.08)" vertical={false} />
          <XAxis
            dataKey="t"
            tick={{ fill: "#6b7c86", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#6b7c86", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: "#f7fafb",
              border: "1px solid #d5dee3",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value: number) => [`${value}${unit}`, "value"]}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            fill="url(#fill)"
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
