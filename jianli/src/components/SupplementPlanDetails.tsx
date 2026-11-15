/** The saved plan's three fields share the same reading order across both scopes. */
export default function SupplementPlanDetails({ deliverable, steps, acceptanceChecks }: {
  deliverable: string; steps: readonly string[]; acceptanceChecks: readonly string[];
}) {
  return <>
    {deliverable && <div>
      <p className="font-medium">提交什么</p>
      <p className="whitespace-pre-wrap break-words">{deliverable}</p>
    </div>}
    {steps.length > 0 && <div>
      <p className="font-medium">执行步骤</p>
      <ol className="list-decimal space-y-1 pl-5">{steps.map((step, index) => <li key={index} className="whitespace-pre-wrap break-words">{step}</li>)}</ol>
    </div>}
    {acceptanceChecks.length > 0 && <div>
      <p className="font-medium">核对项</p>
      <ul className="list-disc space-y-1 pl-5">{acceptanceChecks.map((check, index) => <li key={index} className="whitespace-pre-wrap break-words">{check}</li>)}</ul>
    </div>}
  </>;
}
