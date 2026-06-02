import { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { Toolbar } from './components/Toolbar';
import { Table } from './components/Table';
import { Drawer } from './components/Drawer';
import { Pagination } from './components/Pagination';
import { AppModal } from './components/AppModal';
import { ResumeTab } from './components/ResumeTab';
import {
  fetchApplications, fetchHistory, fetchStats,
  createApplication, updateApplication, deleteApplication,
} from './services/api';

function App() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({});
  const [activeCount, setActiveCount] = useState(0);

  // Tab
  const [activeTab, setActiveTab] = useState('tracker');

  // Filters & Pagination
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [sortField, setSortField] = useState('applied_date');
  const [sortDir, setSortDir] = useState('desc');
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [needsReview, setNeedsReview] = useState(false);
  const [pagination, setPagination] = useState({ total: 0, total_pages: 0 });

  // Drawer
  const [selectedId, setSelectedId] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerApp, setDrawerApp] = useState(null);
  const [drawerHistory, setDrawerHistory] = useState([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    const handler = setTimeout(() => { loadData(); }, 300);
    return () => clearTimeout(handler);
  }, [page, sortField, sortDir, status, search, dateFrom, dateTo, needsReview]);

  useEffect(() => { loadStats(); }, []);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        page, limit,
        sort_by: sortField,
        sort_dir: sortDir,
        status,
        company: search,
        date_from: dateFrom,
        date_to: dateTo,
      };
      if (needsReview) params.needs_review = true;
      const resp = await fetchApplications(params);
      setApps(resp.data || []);
      setPagination(resp.pagination || { total: 0, total_pages: 0 });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const data = await fetchStats();
      setStats({ total: data.total, interview: data.interview, rejected: data.rejected, offer: data.offer });
      setActiveCount(data.needs_review);
    } catch (err) {
      console.error('Failed to load stats', err);
    }
  };

  const handleRowClick = async (id) => {
    setSelectedId(id);
    setDrawerOpen(true);
    setDrawerLoading(true);
    try {
      const appData = apps.find(a => a.id === id);
      setDrawerApp(appData || null);
      const historyData = await fetchHistory(id);
      setDrawerHistory(historyData.data || []);
    } catch (err) {
      console.error('Failed to load drawer data', err);
    } finally {
      setDrawerLoading(false);
    }
  };

  const closeDrawer = () => { setSelectedId(null); setDrawerOpen(false); };

  const handleSort = (field) => {
    if (sortField === field) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
    setPage(1);
  };

  const handleCreate = async (data) => {
    await createApplication(data);
    await loadData();
    await loadStats();
  };

  const handleUpdate = async (id, data) => {
    const updated = await updateApplication(id, data);
    setDrawerApp(updated);
    // Refresh list row in-place
    setApps(prev => prev.map(a => a.id === id ? { ...a, ...updated } : a));
    await loadStats();
  };

  const handleDelete = async (id) => {
    await deleteApplication(id);
    // The default list excludes soft-deleted rows, so just refetch.
    setApps(prev => prev.filter(a => a.id !== id));
    await loadStats();
  };

  const handleApplicationLogged = async () => {
    await loadData();
    await loadStats();
  };

  return (
    <div className="app-shell">
      {error && <div className="error-bar visible">{error}</div>}

      <Header
        stats={stats}
        activeCount={activeCount}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {activeTab === 'tracker' ? (
        <div className="tracker-layout">
          <Toolbar
            search={search} onSearchChange={(v) => { setSearch(v); setPage(1); }}
            dateFrom={dateFrom} onDateFromChange={(v) => { setDateFrom(v); setPage(1); }}
            dateTo={dateTo} onDateToChange={(v) => { setDateTo(v); setPage(1); }}
            status={status} onStatusChange={(v) => { setStatus(v); setPage(1); }}
            needsReview={needsReview} onNeedsReviewChange={(v) => { setNeedsReview(v); setPage(1); }}
            onLogApplication={() => setModalOpen(true)}
          />

          <div className="main">
            <div className="table-pane">
              <Table
                data={apps}
                loading={loading}
                selectedId={selectedId}
                onRowClick={handleRowClick}
                sort={{ field: sortField, dir: sortDir }}
                onSort={handleSort}
              />
            </div>
            <Drawer
              app={drawerApp}
              history={drawerHistory}
              loading={drawerLoading}
              isOpen={drawerOpen}
              onClose={closeDrawer}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          </div>

          <Pagination
            page={page}
            limit={limit}
            total={pagination.total}
            totalPages={pagination.total_pages}
            onPageChange={setPage}
          />

          <AppModal
            isOpen={modalOpen}
            onClose={() => setModalOpen(false)}
            onCreate={handleCreate}
          />
        </div>
      ) : (
        <div className="resume-shell">
          <ResumeTab onApplicationLogged={handleApplicationLogged} />
        </div>
      )}
    </div>
  );
}

export default App;
