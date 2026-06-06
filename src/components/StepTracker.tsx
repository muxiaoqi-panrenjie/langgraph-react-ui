import React from "react";
import type { StreamStep } from "../services/langgraph";
import { Play, CheckCircle2, AlertCircle, Wrench, Loader2, PauseCircle } from "lucide-react";

interface StepTrackerProps {
  steps: StreamStep[];
  isStreaming: boolean;
}

export const StepTracker: React.FC<StepTrackerProps> = ({ steps, isStreaming }) => {
  return (
    <div className="w-80 border-l border-slate-800 bg-[#0d0e12]/80 backdrop-blur-xl flex flex-col h-full text-slate-200">
      {/* 顶部标题区 */}
      <div className="p-5 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="font-bold text-sm text-white">图执行轨迹 (Graph Run)</h2>
          <p className="text-xxs text-slate-500 font-mono mt-0.5">节点流转轨迹与工具分析</p>
        </div>
        {isStreaming && (
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
        )}
      </div>

      {/* 步骤时间轴 */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar">
        {steps.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-slate-600 space-y-2 py-12">
            <Play className="w-8 h-8 text-slate-800 animate-pulse" />
            <div className="font-semibold text-slate-500 text-xs">等待图执行...</div>
            <p className="text-xxs text-slate-600 max-w-[180px] leading-relaxed">
              当智能体被激活时，其底层的状态图转移过程会实时显示在此处。
            </p>
          </div>
        ) : (
          <div className="relative border-l border-slate-800 ml-4 space-y-6">
            {steps.map((step, idx) => {
              const dateStr = new Date(step.timestamp).toLocaleTimeString([], {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              });

              let icon = <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
              let statusText = "执行完毕";
              let statusBg = "bg-slate-900 border-slate-800";

              if (step.status === "thinking") {
                icon = <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />;
                statusText = "思考决策中";
                statusBg = "bg-indigo-950/40 border-indigo-500/20";
              } else if (step.status === "calling_tool") {
                icon = <Wrench className="w-4 h-4 text-amber-400 animate-bounce" />;
                statusText = `正在调用工具`;
                statusBg = "bg-amber-950/20 border-amber-500/20";
              } else if (step.status === "interrupted") {
                icon = <PauseCircle className="w-4 h-4 text-red-400" />;
                statusText = "等待人工审批";
                statusBg = "bg-red-950/30 border-red-500/20";
              }

              return (
                <div key={idx} className="relative pl-7 transition-all duration-300 animate-fadeIn">
                  {/* 时间轴圆形标记 */}
                  <div className={`absolute -left-[9px] top-1.5 w-4 h-4 rounded-full border flex items-center justify-center shadow-lg ${statusBg}`}>
                    {step.status === "thinking" ? (
                      <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-ping" />
                    ) : step.status === "calling_tool" ? (
                      <div className="w-1.5 h-1.5 bg-amber-400 rounded-full" />
                    ) : (
                      <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                    )}
                  </div>

                  {/* 步骤内容卡片 */}
                  <div className={`p-3 rounded-xl border transition-all ${
                    step.status === "thinking"
                      ? "bg-indigo-950/20 border-indigo-500/10 text-indigo-200"
                      : step.status === "calling_tool"
                      ? "bg-amber-950/10 border-amber-500/10 text-amber-200"
                      : step.status === "interrupted"
                      ? "bg-red-950/10 border-red-500/10 text-red-200"
                      : "bg-[#13141a] border-slate-800/80 text-slate-300"
                  }`}>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold font-mono text-white">
                        节点: {step.node}
                      </span>
                      <span className="text-xxs font-mono text-slate-500">{dateStr}</span>
                    </div>

                    <div className="flex items-center gap-1.5 mt-2 text-xxs font-semibold">
                      {icon}
                      <span>{statusText}</span>
                    </div>

                    {step.toolName && (
                      <div className="mt-2 bg-slate-950/60 border border-slate-900 rounded-lg p-2 font-mono text-xxs text-amber-400/90 leading-relaxed break-all">
                        <div className="text-slate-500 text-[9px] font-semibold mb-0.5">TOOL ARGS & EXEC:</div>
                        {step.toolName}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 底部运行提示 */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/20 text-xxs text-slate-600 font-mono flex items-center gap-2">
        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
        <span>支持 stream_mode="updates" 调试</span>
      </div>
    </div>
  );
};
