// 传智杯44：投递提交管线。忙碌期间单飞防重；失败后 busy 归零可直接重试，
// 发布式状态与 application-list-session 同风格，便于无 DOM 回归。
export interface ApplicationSubmitState {
  busy: boolean;
  // 空串表示当前没有需要展示的提示。
  notice: string;
  // 最近一次提交是否成功：决定提示的语义颜色（成功靛蓝/失败玫红）。
  done: boolean;
}

export function createApplicationSubmitSession(
  api: { submit(): Promise<unknown>; errorMessage(error: unknown): string },
  publish: (value: ApplicationSubmitState) => void,
) {
  let inFlight = false;
  return {
    async submit() {
      if (inFlight) return;
      inFlight = true;
      publish({ busy: true, notice: "", done: false });
      try {
        await api.submit();
        inFlight = false;
        publish({ busy: false, notice: "已投递，可在“我的投递”查看企业回应与撤回授权。", done: true });
      } catch (error) {
        inFlight = false;
        const status = (error as {status?: number} | null)?.status;
        const unknown = status === undefined || status < 400 || status === 408 || status >= 500;
        // A lost response does not establish failure; never automatically send again.
        const notice = unknown
          ? `投递结果尚未确认：${api.errorMessage(error)}。请先到“我的投递”查看；如需重试，将仍使用本次报告版本。`
          : api.errorMessage(error);
        publish({ busy: false, notice, done: false });
      }
    },
  };
}
