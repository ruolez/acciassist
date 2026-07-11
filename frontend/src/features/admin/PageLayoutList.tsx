import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ReactNode } from "react";

import type { Question } from "../../api/types";
import { mergeWithNext, moveQuestion, splitPage } from "./page-layout";

type Props = {
  pages: Question[][];
  onLayoutChange: (pages: number[][]) => void;
  renderItem: (question: Question) => ReactNode;
};

function Row({ id, children }: { id: number; children: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  return (
    <div
      ref={setNodeRef}
      className={`sortable-row ${isDragging ? "dragging" : ""}`}
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      <button className="drag-handle" {...attributes} {...listeners} aria-label="Drag">
        ⋮⋮
      </button>
      <div className="sortable-content">{children}</div>
    </div>
  );
}

export function PageLayoutList({ pages, onLayoutChange, renderItem }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );
  const allIds = pages.flat().map((q) => q.id);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    onLayoutChange(moveQuestion(pages, Number(active.id), Number(over.id)));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={allIds} strategy={verticalListSortingStrategy}>
        {pages.map((page, pageIndex) => (
          <div key={page[0].id} className="page-card">
            <div className="page-card-head">
              <span>Page {pageIndex + 1}</span>
              {page.length > 1 && <span className="muted">{page.length} questions</span>}
            </div>
            {page.map((q, pos) => (
              <div key={q.id}>
                <Row id={q.id}>{renderItem(q)}</Row>
                {pos < page.length - 1 && (
                  <button
                    type="button"
                    className="page-divider"
                    onClick={() => onLayoutChange(splitPage(pages, pageIndex, pos))}
                  >
                    ✂ Split into new page
                  </button>
                )}
              </div>
            ))}
            {pageIndex < pages.length - 1 && (
              <button
                type="button"
                className="page-merge"
                onClick={() => onLayoutChange(mergeWithNext(pages, pageIndex))}
              >
                ⇩ Merge with next page
              </button>
            )}
          </div>
        ))}
      </SortableContext>
    </DndContext>
  );
}
