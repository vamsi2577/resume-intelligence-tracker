export function Pagination({ page, limit, total, totalPages, onPageChange }) {
  if (total === 0) return null;

  const from = (page - 1) * limit + 1;
  const to = Math.min(page * limit, total);
  
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  const pages = [];
  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  return (
    <div className="pagination">
      <div className="pagination-info">
        {from}–{to} of {total} applications
      </div>
      <div className="pagination-btns">
        <button 
          className="pg-btn" 
          onClick={() => onPageChange(page - 1)} 
          disabled={page === 1}
        >
          ← Prev
        </button>
        {pages.map(i => (
          <button 
            key={i}
            className={`pg-btn ${i === page ? 'active' : ''}`}
            onClick={() => onPageChange(i)}
          >
            {i}
          </button>
        ))}
        <button 
          className="pg-btn" 
          onClick={() => onPageChange(page + 1)} 
          disabled={page >= totalPages}
        >
          Next →
        </button>
      </div>
    </div>
  );
}
