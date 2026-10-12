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
        // 失败提示原样展示，按钮恢复可用，用户再次点击即为重试。
        publish({ busy: false, notice: api.errorMessage(error), done: false });
      }
    },
  };
}
