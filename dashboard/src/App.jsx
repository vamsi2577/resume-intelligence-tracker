import { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { Toolbar } from './components/Toolbar';
import { Table } from './components/Table';
import { Drawer } from './components/Drawer';
import { Pagination } from './components/Pagination';
import { fetchApplications, fetchHistory, fetchAllApps } from './services/api';

function App() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({});
  const [activeCount, setActiveCount] = useState(0);

  // Filters & Pagination state
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [sortField, setSortField] = useState('applied_date');
  const [sortDir, setSortDir] = useState('desc');
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [pagination, setPagination] = useState({ total: 0, total_pages: 0 });

  // Drawer state
  const [selectedId, setSelectedId] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerApp, setDrawerApp] = useState(null);
  const [drawerHistory, setDrawerHistory] = useState([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  useEffect(() => {
    const handler = setTimeout(() => {
      loadData();
    }, 300);
    return () => clearTimeout(handler);
  }, [page, sortField, sortDir, status, search, dateFrom, dateTo]);

  useEffect(() => {
    loadStats();
  }, []);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchApplications({
        page,
        limit,
        sort_by: sortField,
        sort_dir: sortDir,
        status,
        company: search,
        date_from: dateFrom,
        date_to: dateTo,
      });
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
      const allData = await fetchAllApps();
      if (!allData) return;
      const data = allData.data || [];
      const statsObj = {
        total: allData.pagination.total,
        interview: data.filter(a => a.status === 'interview').length,
        rejected: data.filter(a => a.status === 'rejected').length,
        offer: data.filter(a => ['offer', 'offer_accepted'].includes(a.status)).length,
      };
      setStats(statsObj);

      const cutoff = new Date(); 
      cutoff.setDate(cutoff.getDate() - 14);
      const needsReview = data.filter(a =>
        ['applied','screening'].includes(a.status) &&
        new Date(a.applied_date) < cutoff
      ).length;
      setActiveCount(needsReview);
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

  const closeDrawer = () => {
    setSelectedId(null);
    setDrawerOpen(false);
  };

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
    setPage(1);
  };

  return (
    <>
      {error && <div className="error-bar visible">{error}</div>}
      
      <Header stats={stats} activeCount={activeCount} />
      
      <Toolbar 
        search={search} onSearchChange={(v) => { setSearch(v); setPage(1); }}
        dateFrom={dateFrom} onDateFromChange={(v) => { setDateFrom(v); setPage(1); }}
        dateTo={dateTo} onDateToChange={(v) => { setDateTo(v); setPage(1); }}
        status={status} onStatusChange={(v) => { setStatus(v); setPage(1); }}
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
        />
      </div>

      <Pagination 
        page={page} 
        limit={limit}
        total={pagination.total} 
        totalPages={pagination.total_pages} 
        onPageChange={setPage} 
      />
    </>
  );
}

export default App;
