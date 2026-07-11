import type { CaseStage } from "../../api/types";
import { CASE_STAGES, STAGE_LABELS } from "./stages";

type Props = { stage: CaseStage };

export function StageProgress({ stage }: Props) {
  const currentIndex = CASE_STAGES.indexOf(stage);
  return (
    <div className="stage-progress" role="list" aria-label="Case progress">
      {CASE_STAGES.map((s, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "current" : "";
        return (
          <div key={s} role="listitem" className={`stage-step ${state}`}>
            <span className="stage-step-bar" />
            <span className="stage-step-label">{STAGE_LABELS[s]}</span>
          </div>
        );
      })}
    </div>
  );
}
