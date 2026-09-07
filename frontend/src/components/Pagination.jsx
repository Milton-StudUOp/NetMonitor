import React from 'react';
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight } from 'lucide-react';

export default function Pagination({ page, pageSize, total, count, onPageChange, disabled = false }) {
  const totalPages = total == null ? null : Math.max(1, Math.ceil(total / pageSize));
  const hasPrevious = page > 1;
  const hasNext = totalPages == null ? count === pageSize : page < totalPages;
  const start = count ? ((page - 1) * pageSize) + 1 : 0;
  const end = count ? start + count - 1 : 0;

  return <nav className="data-pagination" aria-label="Table pagination">
    <div className="pagination-summary">
      <strong>{start.toLocaleString()}–{end.toLocaleString()}</strong>
      <span>{total == null ? 'records on this result set' : `of ${total.toLocaleString()} records`}</span>
    </div>
    <div className="pagination-controls">
      <button type="button" title="First page" aria-label="First page" disabled={disabled || !hasPrevious} onClick={() => onPageChange(1)}><ChevronFirst size={16}/></button>
      <button type="button" title="Previous page" aria-label="Previous page" disabled={disabled || !hasPrevious} onClick={() => onPageChange(page - 1)}><ChevronLeft size={16}/><span>Previous</span></button>
      <span className="pagination-page">Page <strong>{page}</strong>{totalPages != null && <> of <strong>{totalPages}</strong></>}</span>
      <button type="button" title="Next page" aria-label="Next page" disabled={disabled || !hasNext} onClick={() => onPageChange(page + 1)}><span>Next</span><ChevronRight size={16}/></button>
      {totalPages != null && <button type="button" title="Last page" aria-label="Last page" disabled={disabled || !hasNext} onClick={() => onPageChange(totalPages)}><ChevronLast size={16}/></button>}
    </div>
  </nav>;
}
