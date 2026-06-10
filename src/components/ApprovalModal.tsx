import React, { useState, useEffect } from "react";
import type { InterruptData, ApprovalDecision, Assistant } from "../services/langgraph";
import { Shield, AlertTriangle, Mail, Trash2, ShoppingCart, Check, X, Edit3, Headphones } from "lucide-react";

interface ApprovalModalProps {
  interrupt: InterruptData;
  assistant: Assistant | null;
  onApprove: (decision: ApprovalDecision) => void;
  onReject: (decision: ApprovalDecision) => void;
  onEdit: (decision: ApprovalDecision) => void;
}

/**
 * HITL 审批弹窗组件
 * 对应 notebook 中的人机协同模式：approve / reject / edit
 */
export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  interrupt,
  assistant,
  onApprove,
  onReject,
  onEdit,
}) => {
  const [showEditForm, setShowEditForm] = useState(false);
  const [editFields, setEditFields] = useState<Record<string, string>>({});

  // 根据工具名称初始化编辑字段
  useEffect(() => {
    setEditFields(
      Object.fromEntries(
        Object.entries(interrupt.args).map(([k, v]) => [k, String(v)])
      )
    );
    if (interrupt.tool_name === "human_agent_reply") {
      setShowEditForm(true);
    } else {
      setShowEditForm(false);
    }
  }, [interrupt]);

  const isHighSeverity = interrupt.severity === "high";
  const isHumanReply = interrupt.tool_name === "human_agent_reply";

  // 根据工具类型选择图标和颜色
  const getIcon = () => {
    switch (interrupt.tool_name) {
      case "send_email":
      case "send_email_hitl":
        return <Mail className="w-5 h-5" />;
      case "delete_database":
        return <Trash2 className="w-5 h-5" />;
      case "make_purchase":
        return <ShoppingCart className="w-5 h-5" />;
      case "human_agent_reply":
        return <Headphones className="w-5 h-5" />;
      default:
        return <Shield className="w-5 h-5" />;
    }
  };

  const getToolLabel = () => {
    switch (interrupt.tool_name) {
      case "send_email":
      case "send_email_hitl":
        return "发送邮件";
      case "delete_database":
        return "删除数据库";
      case "make_purchase":
        return "采购审批";
      case "human_agent_reply":
        return "人工客服回复";
      default:
        return interrupt.tool_name;
    }
  };

  const handleApprove = () => {
    const decision: ApprovalDecision = {
      action: "approve",
      ...interrupt.args,
    };
    onApprove(decision);
  };

  const handleReject = () => {
    const decision: ApprovalDecision = { action: "reject" };
    onReject(decision);
  };

  const handleEditSubmit = () => {
    const decision: ApprovalDecision = {
      action: "edit",
      ...editFields,
    };
    onEdit(decision);
    setShowEditForm(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn">
      <div
        className={`w-[480px] max-h-[80vh] overflow-y-auto rounded-2xl border shadow-2xl bg-[#13151a] ${
          isHumanReply
            ? "border-indigo-500/30 shadow-indigo-500/10"
            : isHighSeverity
            ? "border-red-500/30 shadow-red-500/10"
            : "border-amber-500/30 shadow-amber-500/10"
        }`}
      >
        {/* 头部 */}
        <div
          className={`px-6 py-4 border-b flex items-center gap-3 ${
            isHumanReply
              ? "border-indigo-500/20 bg-indigo-950/20"
              : isHighSeverity
              ? "border-red-500/20 bg-red-950/20"
              : "border-amber-500/20 bg-amber-950/20"
          }`}
        >
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              isHumanReply
                ? "bg-indigo-950/50 text-indigo-400 border border-indigo-500/20"
                : isHighSeverity
                ? "bg-red-950/50 text-red-400 border border-red-500/20"
                : "bg-amber-950/50 text-amber-400 border border-amber-500/20"
            }`}
          >
            {getIcon()}
          </div>
          <div className="flex-1">
            <h3 className="font-bold text-sm text-white">
              {isHumanReply
                ? "🎧 人工客服接入兜底"
                : isHighSeverity
                ? "⚠️ 高风险操作审批"
                : "🔒 操作审批"}
            </h3>
            <p className="text-xxs text-slate-500 font-mono mt-0.5">
              智能体 ({assistant?.name}) 请求执行：{getToolLabel()}
            </p>
          </div>
          {isHighSeverity && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-red-400 bg-red-950/40 border border-red-500/20 px-2 py-0.5 rounded-full">
              <AlertTriangle className="w-3 h-3" />
              HIGH
            </span>
          )}
          {isHumanReply && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 bg-indigo-950/40 border border-indigo-500/20 px-2 py-0.5 rounded-full">
              HUMAN
            </span>
          )}
        </div>

        {/* 提示消息 */}
        <div className="px-6 py-3">
          <p className="text-sm text-slate-300 leading-relaxed">{interrupt.message}</p>
        </div>

        {/* 参数详情 */}
        {!showEditForm ? (
          <div className="px-6 pb-4 space-y-2">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              操作参数
            </div>
            {Object.entries(interrupt.args).map(([key, value]) => (
              <div key={key} className="bg-slate-950/50 border border-slate-800 rounded-lg p-3">
                <div className="text-[10px] font-mono text-slate-500 mb-1 uppercase">{key}</div>
                <div className="text-xs font-mono text-slate-200 break-all whitespace-pre-wrap">
                  {String(value)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* 编辑表单 */
          <div className="px-6 pb-4 space-y-3">
            <div className="flex items-center gap-2 text-[10px] font-bold text-indigo-400 uppercase tracking-wider mb-1">
              <Edit3 className="w-3.5 h-3.5" />
              编辑参数
            </div>
            {Object.entries(editFields).map(([key, value]) => (
              <div key={key}>
                <label className="text-[10px] font-mono text-slate-500 uppercase block mb-1">
                  {key}
                </label>
                <input
                  type="text"
                  value={value}
                  onChange={(e) =>
                    setEditFields((prev) => ({ ...prev, [key]: e.target.value }))
                  }
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-all"
                />
              </div>
            ))}
          </div>
        )}

        {/* 操作按钮 */}
        <div className="px-6 py-4 border-t border-slate-800/60 flex items-center gap-3">
          <button
            onClick={handleReject}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-red-950/30 border border-red-500/20 text-red-400 text-xs font-semibold hover:bg-red-950/50 transition-all active:scale-95"
          >
            <X className="w-3.5 h-3.5" />
            拒绝
          </button>
          {!showEditForm ? (
            <button
              onClick={() => setShowEditForm(true)}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition-all active:scale-95"
            >
              <Edit3 className="w-3.5 h-3.5" />
              编辑
            </button>
          ) : (
            <button
              onClick={handleEditSubmit}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 border border-indigo-500/50 text-white text-xs font-semibold hover:bg-indigo-500 transition-all active:scale-95"
            >
              <Check className="w-3.5 h-3.5" />
              确认编辑
            </button>
          )}
          <button
            onClick={handleApprove}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-950/30 border border-emerald-500/20 text-emerald-400 text-xs font-semibold hover:bg-emerald-950/50 transition-all active:scale-95"
          >
            <Check className="w-3.5 h-3.5" />
            批准
          </button>
        </div>
      </div>
    </div>
  );
};
